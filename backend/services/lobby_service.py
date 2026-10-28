"""Lobby management service — validation + Supabase operations.

Validation rules are pure functions (unit-testable); Supabase calls are
isolated in the bottom section. Joins/leaves go through the atomic DB
functions `join_lobby` / `leave_lobby` (migration 005) so simultaneous
requests can never overbook a lobby.
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Constants & pure validation
# ---------------------------------------------------------------------------
MIN_TEAM_SIZE = 1
MAX_TEAM_SIZE = 15
MIN_TOTAL_PLAYERS = 2
MAX_TOTAL_PLAYERS = 30
TITLE_RE = re.compile(r"^.{3,100}$")

LOBBY_STATUS_CODES = ("open", "full", "in_progress", "completed", "cancelled")


class LobbyValidationError(Exception):
    """Raised when lobby input or a state transition is invalid."""


def validate_lobby_input(data: dict) -> dict:
    """Validate create-lobby payload; returns normalised fields.

    Required: sport_id, title, latitude, longitude, scheduled_at (ISO 8601
    future), team_size, max_players. Optional: ground_id, description,
    min_players (default = team_size... actually min = 2*team_size floor).
    """
    if not isinstance(data, dict):
        raise LobbyValidationError("Body must be a JSON object.")

    sport_id = str(data.get("sport_id") or "")
    if len(sport_id) != 36:
        raise LobbyValidationError("A valid sport_id is required.")

    title = str(data.get("title") or "").strip()
    if not TITLE_RE.match(title):
        raise LobbyValidationError("Title must be 3-100 characters.")

    try:
        lat = float(data["latitude"])
        lon = float(data["longitude"])
    except (KeyError, TypeError, ValueError):
        raise LobbyValidationError("Valid latitude and longitude are required.")
    if not (-90 <= lat <= 90):
        raise LobbyValidationError("Latitude must be between -90 and 90.")
    if not (-180 <= lon <= 180):
        raise LobbyValidationError("Longitude must be between -180 and 180.")

    when = parse_future_datetime(data.get("scheduled_at"))

    try:
        team_size = int(data["team_size"])
        max_players = int(data["max_players"])
    except (KeyError, TypeError, ValueError):
        raise LobbyValidationError("team_size and max_players must be integers.")

    if not (MIN_TEAM_SIZE <= team_size <= MAX_TEAM_SIZE):
        raise LobbyValidationError(f"team_size must be {MIN_TEAM_SIZE}-{MAX_TEAM_SIZE}.")
    if not (MIN_TOTAL_PLAYERS <= max_players <= MAX_TOTAL_PLAYERS):
        raise LobbyValidationError(
            f"max_players must be {MIN_TOTAL_PLAYERS}-{MAX_TOTAL_PLAYERS}."
        )
    # A match needs at least enough players for the configured teams.
    if max_players < team_size * 2:
        raise LobbyValidationError(
            f"max_players must be at least 2 × team_size ({team_size * 2})."
        )

    min_players = data.get("min_players", team_size * 2)
    try:
        min_players = int(min_players)
    except (TypeError, ValueError):
        raise LobbyValidationError("min_players must be an integer.")
    if not (team_size * 2 <= min_players <= max_players):
        raise LobbyValidationError(
            f"min_players must be between {team_size * 2} and {max_players}."
        )

    ground_id = data.get("ground_id") or None
    if ground_id is not None and len(str(ground_id)) != 36:
        raise LobbyValidationError("ground_id must be a valid id.")

    description = data.get("description")
    if description and len(str(description)) > 1000:
        raise LobbyValidationError("Description must be at most 1000 characters.")

    return {
        "sport_id": sport_id,
        "ground_id": ground_id,
        "title": title,
        "description": description or None,
        "latitude": lat,
        "longitude": lon,
        "scheduled_at": when.isoformat(),
        "team_size": team_size,
        "min_players": min_players,
        "max_players": max_players,
    }


def parse_future_datetime(value) -> datetime:
    """Parse ISO 8601; must be in the future (allow 5 min clock slack)."""
    if not value:
        raise LobbyValidationError("scheduled_at is required.")
    try:
        when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise LobbyValidationError("scheduled_at must be ISO 8601, e.g. 2026-11-01T18:30.")
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    if when < datetime.now(timezone.utc) - timedelta(minutes=5):
        raise LobbyValidationError("scheduled_at must be in the future.")
    return when


def can_transition(current: str, target: str) -> bool:
    """Allowed lobby state machine:
    open -> full -> in_progress -> completed
      \\--------------------------------/ (any non-final -> cancelled)
    """
    allowed = {
        "open": {"full", "in_progress", "cancelled"},
        "full": {"open", "in_progress", "cancelled"},
        "in_progress": {"completed", "cancelled"},
        "completed": set(),
        "cancelled": set(),
    }
    return target in allowed.get(current, set())


def check_join_preconditions(lobby: dict, places_available: int) -> None:
    """Client-side pre-checks (the DB function is authoritative).

    Used to return friendly errors before hitting the RPC.
    """
    if lobby.get("status") != "open":
        raise LobbyValidationError("This lobby is not open for joining.")
    if places_available <= 0:
        raise LobbyValidationError("This lobby is full.")
    return None


def check_start_preconditions(lobby: dict, joined: int, user_id: str) -> None:
    if lobby["host_id"] != user_id:
        raise LobbyValidationError("Only the host can start the match.")
    if not can_transition(lobby["status"], "in_progress"):
        raise LobbyValidationError(f"Cannot start a lobby in '{lobby['status']}' state.")
    if joined < lobby["min_players"]:
        raise LobbyValidationError(
            f"Need at least {lobby['min_players']} players to start "
            f"({joined} joined)."
        )


def check_cancel_preconditions(lobby: dict, user_id: str) -> None:
    if lobby["host_id"] != user_id:
        raise LobbyValidationError("Only the host can cancel the lobby.")
    if not can_transition(lobby["status"], "cancelled"):
        raise LobbyValidationError(f"Cannot cancel a lobby in '{lobby['status']}' state.")


# ---------------------------------------------------------------------------
# Supabase operations (service-role client; server-side only)
# ---------------------------------------------------------------------------
def _admin():
    from supabase import create_client
    from backend.config import config

    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)


RPC_ERROR_MAP = {
    "NOT_AUTHENTICATED": ("You must be signed in.", 401),
    "LOBBY_NOT_FOUND": ("Lobby not found.", 404),
    "ALREADY_JOINED": ("You have already joined this lobby.", 409),
    "LOBBY_NOT_OPEN": ("This lobby is not open for joining.", 409),
    "LOBBY_ALREADY_STARTED": ("This match has already started.", 409),
    "LOBBY_FULL": ("This lobby is full.", 409),
    "LOBBY_NOT_JOINABLE": ("You can no longer leave this lobby.", 409),
    "NOT_A_PARTICIPANT": ("You are not a participant of this lobby.", 404),
}


def rpc_join(lobby_id: str, user_token: str) -> dict:
    """Call join_lobby() AS THE USER (postgrest with user JWT) so that
    auth.uid() inside the function is the real caller, not the service role."""
    from supabase import create_client, ClientOptions
    from backend.config import config

    client = create_client(
        config.SUPABASE_URL,
        config.SUPABASE_ANON_KEY,
        ClientOptions(headers={"Authorization": f"Bearer {user_token}"}),
    )
    try:
        res = client.rpc("join_lobby", {"p_lobby_id": lobby_id}).execute()
        return {"ok": True, "participant": res.data}
    except Exception as exc:  # noqa: BLE001
        return _map_rpc_error(exc)


def rpc_leave(lobby_id: str, user_token: str) -> dict:
    from supabase import create_client, ClientOptions
    from backend.config import config

    client = create_client(
        config.SUPABASE_URL,
        config.SUPABASE_ANON_KEY,
        ClientOptions(headers={"Authorization": f"Bearer {user_token}"}),
    )
    try:
        client.rpc("leave_lobby", {"p_lobby_id": lobby_id}).execute()
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return _map_rpc_error(exc)


def _map_rpc_error(exc) -> dict:
    msg = str(exc)
    for code, (friendly, status) in RPC_ERROR_MAP.items():
        if code in msg:
            return {"ok": False, "error": friendly, "status": status}
    return {"ok": False, "error": "Could not update lobby participation.", "status": 500}


def create_lobby(host_id: str, fields: dict) -> dict:
    admin = _admin()
    res = admin.table("lobbies").insert({**fields, "host_id": host_id}).execute()
    return res.data[0]


def get_lobby(lobby_id: str) -> Optional[dict]:
    try:
        res = (
            _admin()
            .table("lobbies")
            .select(
                "*,sports(id,code,name,icon),"
                "grounds(name,city,address),"
                "profiles!lobbies_host_id_fkey(username,full_name,avatar_url),"
                "lobby_participants(user_id,joined_at,profiles(username,full_name,avatar_url))"
            )
            .eq("id", lobby_id)
            .single()
            .execute()
        )
        return res.data
    except Exception:  # noqa: BLE001
        return None


def update_lobby_status(lobby_id: str, new_status: str) -> Optional[dict]:
    res = _admin().table("lobbies").update({"status": new_status}).eq("id", lobby_id).execute()
    return res.data[0] if res.data else None
