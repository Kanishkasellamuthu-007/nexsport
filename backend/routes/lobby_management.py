"""Lobby management routes (token-verified, host-authorised)."""
from flask import Blueprint, jsonify, request

from backend.services.auth_service import AuthError, verify_request_user
from backend.services import lobby_service as ls
from backend.services.lobby_service import LobbyValidationError

lobbies_mgmt_bp = Blueprint("lobbies_mgmt", __name__, url_prefix="/api/lobbies")


def _user_or_error():
    try:
        return verify_request_user(request), None
    except AuthError as exc:
        return None, (jsonify({"error": exc.message}), exc.status_code)


def _shape(lobby: dict) -> dict:
    """Normalise a lobby row (with joins) for the frontend."""
    participants = lobby.pop("lobby_participants", []) or []
    sport = lobby.pop("sports", None)
    ground = lobby.pop("grounds", None)
    host = lobby.pop("profiles", None) or {}
    return {
        "id": lobby["id"],
        "title": lobby["title"],
        "description": lobby.get("description"),
        "status": lobby["status"],
        "visibility": lobby["visibility"],
        "scheduled_at": lobby["scheduled_at"],
        "team_size": lobby["team_size"],
        "min_players": lobby["min_players"],
        "max_players": lobby["max_players"],
        "latitude": lobby["latitude"],
        "longitude": lobby["longitude"],
        "sport": sport,
        "ground": ground,
        "ground_name": (ground or {}).get("name") or "Custom location",
        "host": {"id": lobby["host_id"], "username": host.get("username")},
        "participants": [
            {
                "user_id": p["user_id"],
                "joined_at": p["joined_at"],
                "username": (p.get("profiles") or {}).get("username"),
            }
            for p in participants
        ],
        "players_joined": len(participants),
        "places_available": max(0, lobby["max_players"] - len(participants)),
    }


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------
@lobbies_mgmt_bp.post("")
def create():
    claims, err = _user_or_error()
    if err:
        return err

    try:
        fields = ls.validate_lobby_input(request.get_json(silent=True) or {})
    except LobbyValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        lobby = ls.create_lobby(claims["sub"], fields)
    except Exception:  # noqa: BLE001
        return jsonify({"error": "Could not create the lobby."}), 500

    return jsonify({"lobby": lobby, "message": "Lobby created!"}), 201


# ---------------------------------------------------------------------------
# Read: my lobbies + detail
# ---------------------------------------------------------------------------
@lobbies_mgmt_bp.get("/mine")
def mine():
    claims, err = _user_or_error()
    if err:
        return err
    try:
        res = (
            ls._admin()
            .table("lobbies")
            .select("*,sports(name,icon)")
            .eq("host_id", claims["sub"])
            .order("scheduled_at")
            .execute()
        )
        return jsonify({"lobbies": res.data}), 200
    except Exception:  # noqa: BLE001
        return jsonify({"error": "Could not load your lobbies."}), 500


@lobbies_mgmt_bp.get("/<lobby_id>")
def detail(lobby_id: str):
    _, err = _user_or_error()
    if err:
        return err
    lobby = ls.get_lobby(lobby_id)
    if not lobby:
        return jsonify({"error": "Lobby not found."}), 404
    return jsonify({"lobby": _shape(lobby)}), 200


# ---------------------------------------------------------------------------
# Join / leave — via atomic DB functions called AS the user
# ---------------------------------------------------------------------------
@lobbies_mgmt_bp.post("/<lobby_id>/join")
def join(lobby_id: str):
    claims, err = _user_or_error()
    if err:
        return err

    lobby = ls.get_lobby(lobby_id)
    if not lobby:
        return jsonify({"error": "Lobby not found."}), 404

    joined = len(lobby.get("lobby_participants") or [])
    # Friendly pre-check; the DB function remains authoritative.
    try:
        ls.check_join_preconditions(lobby, lobby["max_players"] - joined)
    except LobbyValidationError as exc:
        return jsonify({"error": str(exc)}), 409

    result = ls.rpc_join(lobby_id, request.headers["Authorization"].split(" ", 1)[1])
    if not result["ok"]:
        return jsonify({"error": result["error"]}), result["status"]

    return jsonify({"message": "You joined the lobby! 🎉"}), 200


@lobbies_mgmt_bp.post("/<lobby_id>/leave")
def leave(lobby_id: str):
    _, err = _user_or_error()
    if err:
        return err

    result = ls.rpc_leave(lobby_id, request.headers["Authorization"].split(" ", 1)[1])
    if not result["ok"]:
        return jsonify({"error": result["error"]}), result["status"]

    return jsonify({"message": "You left the lobby."}), 200


# ---------------------------------------------------------------------------
# Host controls: start / cancel
# ---------------------------------------------------------------------------
@lobbies_mgmt_bp.post("/<lobby_id>/start")
def start(lobby_id: str):
    claims, err = _user_or_error()
    if err:
        return err

    lobby = ls.get_lobby(lobby_id)
    if not lobby:
        return jsonify({"error": "Lobby not found."}), 404

    joined = len(lobby.get("lobby_participants") or [])
    try:
        ls.check_start_preconditions(lobby, joined, claims["sub"])
    except LobbyValidationError as exc:
        status = 403 if "Only the host" in str(exc) else 409
        return jsonify({"error": str(exc)}), status

    updated = ls.update_lobby_status(lobby_id, "in_progress")
    return jsonify({"lobby": updated, "message": "Match started!"}), 200


@lobbies_mgmt_bp.post("/<lobby_id>/cancel")
def cancel(lobby_id: str):
    claims, err = _user_or_error()
    if err:
        return err

    lobby = ls.get_lobby(lobby_id)
    if not lobby:
        return jsonify({"error": "Lobby not found."}), 404

    try:
        ls.check_cancel_preconditions(lobby, claims["sub"])
    except LobbyValidationError as exc:
        status = 403 if "Only the host" in str(exc) else 409
        return jsonify({"error": str(exc)}), status

    ls.update_lobby_status(lobby_id, "cancelled")
    return jsonify({"message": "Lobby cancelled."}), 200
