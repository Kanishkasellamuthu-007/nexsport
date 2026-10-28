"""Team generation route — runs the balancing algorithm for a full lobby.

Authorization (req. 15): only the HOST may generate teams, and only while
the lobby is eligible (full / min reached, status open or full, match not
started). Assignments are stored via the service role; players cannot edit
them (no user write policy touches lobby_participants.team_side except the
host/owner rules already in place, and regeneration is host-only too).
"""
from flask import Blueprint, jsonify, request

from backend.algorithms.team_split import (
    TeamSplitError,
    improved_zigzag_split,
)
from backend.services.auth_service import AuthError, verify_request_user

teams_bp = Blueprint("teams", __name__)


def _admin():
    from supabase import create_client
    from backend.config import config
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)


@teams_bp.post("/api/lobbies/<lobby_id>/teams")
def generate_teams(lobby_id: str):
    try:
        claims = verify_request_user(request)
    except AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    user_id = claims["sub"]

    admin = _admin()
    try:
        lobby = (
            admin.table("lobbies")
            .select("id,host_id,status,sport_id,team_size,min_players,max_players")
            .eq("id", lobby_id)
            .single()
            .execute()
        ).data
    except Exception:  # noqa: BLE001
        return jsonify({"error": "Lobby not found."}), 404

    if not lobby:
        return jsonify({"error": "Lobby not found."}), 404
    if lobby["host_id"] != user_id:
        return jsonify({"error": "Only the host can generate teams."}), 403
    if lobby["status"] not in ("open", "full"):
        return jsonify({"error": "Teams can only be generated before the match starts."}), 409

    parts = (
        admin.table("lobby_participants")
        .select("user_id")
        .eq("lobby_id", lobby_id)
        .execute()
    ).data or []
    joined = len(parts)
    if joined < lobby["min_players"]:
        return jsonify(
            {"error": f"Not enough players: {joined}/{lobby['min_players']}."}
        ), 409

    # Eligibility: full lobby OR exactly at capacity for the match size used
    # for splitting (max_players). Requirement 14 says full & eligible.
    if joined != lobby["max_players"]:
        return jsonify(
            {"error": f"Teams are generated when the lobby is full "
                      f"({joined}/{lobby['max_players']})."}
        ), 409

    # Current AUTHORITATIVE ratings (read-only here — never modified, req. 12).
    ratings = (
        admin.table("player_ratings")
        .select("user_id,current_rating")
        .eq("sport_id", lobby["sport_id"])
        .execute()
    ).data or []
    rmap = {r["user_id"]: r["current_rating"] for r in ratings}

    players = [{"user_id": p["user_id"], "rating": rmap.get(p["user_id"], 1000)}
               for p in parts]

    try:
        result = improved_zigzag_split(players, expected_count=lobby["max_players"])
    except TeamSplitError as exc:
        return jsonify({"error": str(exc)}), 400

    assignments = [
        {"user_id": player["user_id"], "team_side": side}
        for side in ("team_a", "team_b")
        for player in result[side]
    ]

    try:
        admin.rpc(
            "assign_lobby_teams",
            {
                "p_lobby_id": lobby_id,
                "p_host_id": user_id,
                "p_assignments": assignments,
            },
        ).execute()
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        if "ONLY_LOBBY_HOST" in message:
            return jsonify({"error": "Only the host can assign teams."}), 403
        if "LOBBY_NOT_ASSIGNABLE" in message:
            return jsonify({"error": "Teams can only be assigned before the match starts."}), 409
        if "INVALID_TEAM_ASSIGNMENTS" in message:
            return jsonify({"error": "Team assignments do not match the full lobby."}), 409
        return jsonify({"error": "Could not save team assignments."}), 500

    return jsonify({"message": "Teams generated!", "teams": result}), 200


@teams_bp.get("/api/lobbies/<lobby_id>/teams")
def get_teams(lobby_id: str):
    """View stored assignments for the host or an actual participant."""
    try:
        claims = verify_request_user(request)
    except AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    user_id = claims["sub"]

    try:
        admin = _admin()
        lobby = (
            admin.table("lobbies")
            .select("id,host_id")
            .eq("id", lobby_id)
            .single()
            .execute()
        ).data
        rows = (
            admin.table("lobby_participants")
            .select("user_id,team_side,profiles(username)")
            .eq("lobby_id", lobby_id)
            .execute()
        ).data or []
    except Exception:  # noqa: BLE001
        return jsonify({"error": "Could not load teams."}), 500

    if not lobby:
        return jsonify({"error": "Lobby not found."}), 404
    if lobby["host_id"] != user_id and not any(
        row["user_id"] == user_id for row in rows
    ):
        return jsonify({"error": "Only the lobby host or participants can view teams."}), 403

    teams = {
        "team_a": [r for r in rows if r["team_side"] == "team_a"],
        "team_b": [r for r in rows if r["team_side"] == "team_b"],
        "unassigned": [r for r in rows if r["team_side"] == "unassigned"],
    }
    return jsonify({"teams": teams}), 200
