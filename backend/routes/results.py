"""Match results, statistics & peer feedback routes (token-verified)."""
from flask import Blueprint, jsonify, request

from backend.services.auth_service import AuthError, verify_request_user
from backend.services import elo_service
from backend.services.elo_service import ResultValidationError

results_bp = Blueprint("results", __name__, url_prefix="/api/matches")


def _user_or_error():
    try:
        return verify_request_user(request), None
    except AuthError as exc:
        return None, (jsonify({"error": exc.message}), exc.status_code)


def _admin():
    from supabase import create_client
    from backend.config import config
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)


def _load_match_admin(admin, match_id: str):
    """Match + lobby + participants (service role)."""
    m = admin.table("matches").select("*,lobbies(*)").eq("id", match_id).single().execute()
    if not m.data:
        return None
    lobby = m.data["lobbies"]
    parts = (
        admin.table("lobby_participants")
        .select("user_id,team_side")
        .eq("lobby_id", lobby["id"])
        .execute()
    )
    ratings = (
        admin.table("player_ratings")
        .select("user_id,current_rating,matches_count")
        .eq("sport_id", lobby["sport_id"])
        .execute()
    )
    rmap = {r["user_id"]: r for r in (ratings.data or [])}
    for p in parts.data or []:
        r = rmap.get(p["user_id"], {})
        p["rating"] = r.get("current_rating", 1000)
        p["matches"] = r.get("matches_count", 0)
    return {"match": m.data, "lobby": lobby, "participants": parts.data or []}


def _authorized_submitter(match_ctx: dict, user_id: str) -> bool:
    lobby = match_ctx["lobby"]
    if lobby["host_id"] == user_id:
        return True
    return any(p["user_id"] == user_id for p in match_ctx["participants"])


@results_bp.post("/<match_id>/result")
def submit_result(match_id: str):
    """Record the final score. Elo is applied ATOMICALLY via migration 006.

    Authorization: only the lobby host or a real participant (req. 12).
    Idempotency: RESULT_ALREADY_EXISTS / RATINGS_ALREADY_APPLIED (req. 9).
    """
    claims, err = _user_or_error()
    if err:
        return err
    user_id = claims["sub"]

    try:
        body = elo_service.validate_result_payload(request.get_json(silent=True) or {})
    except ResultValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    admin = _admin()
    try:
        ctx = _load_match_admin(admin, match_id)
    except Exception:  # noqa: BLE001
        return jsonify({"error": "Match not found."}), 404
    if not ctx:
        return jsonify({"error": "Match not found."}), 404

    if not _authorized_submitter(ctx, user_id):
        return jsonify({"error": "Only match participants or the host can submit the result."}), 403

    lobby = ctx["lobby"]
    if lobby["status"] != "in_progress":
        return jsonify({"error": "Results can only be submitted for in-progress matches."}), 409

    team_a = [p for p in ctx["participants"] if p["team_side"] == "team_a"]
    team_b = [p for p in ctx["participants"] if p["team_side"] == "team_b"]
    if not team_a or not team_b:
        return jsonify({"error": "Both teams need at least one assigned player."}), 409

    # Validate BEFORE applying anything (req. 11) — pure computation first.
    try:
        preview = elo_service.compute_team_update(
            team_a, team_b, body["team_a_score"], body["team_b_score"]
        )
    except ResultValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    # Atomic DB application (single transaction, idempotent).
    try:
        applied = elo_service.apply_ratings(
            match_id, team_a, team_b, body["team_a_score"], body["team_b_score"]
        )
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "RESULT_ALREADY_EXISTS" in msg or "RATINGS_ALREADY_APPLIED" in msg:
            return jsonify({"error": "This match result was already processed."}), 409
        if "MATCH_NOT_IN_PROGRESS" in msg:
            return jsonify({"error": "Match is not in progress."}), 409
        if "RATING_STALE" in msg:
            return jsonify({"error": "Ratings changed concurrently — retry."}), 409
        return jsonify({"error": "Could not record result."}), 500

    return jsonify(
        {
            "message": "Result recorded and ratings updated!",
            "scores": {"team_a": body["team_a_score"], "team_b": body["team_b_score"]},
            "rating_changes": preview,
        }
    ), 201


@results_bp.post("/<match_id>/feedback")
def submit_feedback(match_id: str):
    """Peer feedback (1-5 skill + sportsmanship) about OTHER participants."""
    claims, err = _user_or_error()
    if err:
        return err
    reviewer = claims["sub"]

    body = request.get_json(silent=True) or {}
    entries = body.get("reviews") or []
    if not isinstance(entries, list) or not entries:
        return jsonify({"error": "reviews list is required."}), 400

    admin = _admin()
    ctx = _load_match_admin(admin, match_id)
    if not ctx:
        return jsonify({"error": "Match not found."}), 404

    participant_ids = {p["user_id"] for p in ctx["participants"]}
    if reviewer not in participant_ids:
        return jsonify({"error": "Only match participants can give feedback."}), 403
    if ctx["lobby"]["status"] != "completed":
        return jsonify({"error": "Feedback opens after the match is completed."}), 409

    rows = []
    for e in entries:
        try:
            reviewee = str(e["reviewee_id"])
            skill = int(e["skill_score"])
            sports = int(e["sportsmanship_score"])
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": "Each review needs reviewee_id, skill_score, sportsmanship_score."}), 400
        if reviewee == reviewer:
            return jsonify({"error": "You cannot review yourself."}), 400
        if reviewee not in participant_ids:
            return jsonify({"error": "Reviewee did not play in this match."}), 400
        if not (1 <= skill <= 5 and 1 <= sports <= 5):
            return jsonify({"error": "Scores must be 1-5."}), 400
        rows.append(
            {"match_id": match_id, "reviewer_id": reviewer, "reviewee_id": reviewee,
             "skill_score": skill, "sportsmanship_score": sports,
             "comment": (e.get("comment") or "")[:500] or None}
        )

    try:
        admin.table("peer_feedback").upsert(
            rows, on_conflict="match_id,reviewer_id,reviewee_id"
        ).execute()
    except Exception:  # noqa: BLE001
        return jsonify({"error": "Could not save feedback."}), 500

    return jsonify({"message": "Feedback saved. Thank you!"}), 201


@results_bp.post("/<match_id>/statistics")
def submit_statistics(match_id: str):
    """Record statistics for a player's own completed match."""
    claims, err = _user_or_error()
    if err:
        return err
    user_id = claims["sub"]

    body = request.get_json(silent=True) or {}
    team_side = body.get("team_side")

    try:
        ctx = _load_match_admin(_admin(), match_id)
    except Exception:  # noqa: BLE001
        return jsonify({"error": "Match not found."}), 404
    if not ctx:
        return jsonify({"error": "Match not found."}), 404

    participant = next(
        (p for p in ctx["participants"] if p["user_id"] == user_id), None
    )
    if not participant:
        return jsonify({"error": "Only match participants can submit statistics."}), 403
    if ctx["lobby"]["status"] != "completed":
        return jsonify({"error": "Statistics can only be submitted after the match is completed."}), 409

    authoritative_team = participant["team_side"]
    if team_side not in ("team_a", "team_b", "unassigned"):
        return jsonify({"error": "team_side must be team_a|team_b|unassigned."}), 400
    if team_side != authoritative_team:
        return jsonify({"error": "team_side does not match the participant's assigned team."}), 409

    custom = body.get("custom_stats") or {}
    if not isinstance(custom, dict):
        return jsonify({"error": "custom_stats must be an object."}), 400

    goals = body.get("goals", 0)
    assists = body.get("assists", 0)
    if not all(isinstance(value, int) and value >= 0 for value in (goals, assists)):
        return jsonify({"error": "goals/assists must be non-negative integers."}), 400

    try:
        _admin().table("match_statistics").upsert(
            {
                "match_id": match_id,
                "user_id": user_id,
                "team_side": authoritative_team,
                "goals": goals,
                "assists": assists,
                "custom_stats": custom,
            },
            on_conflict="match_id,user_id",
        ).execute()
    except Exception:  # noqa: BLE001
        return jsonify({"error": "Could not save statistics."}), 500

    return jsonify({"message": "Statistics saved."}), 201
