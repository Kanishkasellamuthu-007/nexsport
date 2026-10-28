"""Player rating endpoints — display current ratings & history."""
from flask import Blueprint, jsonify, request

from backend.services.auth_service import AuthError, verify_request_user

ratings_bp = Blueprint("ratings", __name__, url_prefix="/api/ratings")


def _admin():
    from supabase import create_client
    from backend.config import config
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)


@ratings_bp.get("/me")
def my_ratings():
    """Current ratings (per sport) + last 20 history rows for the caller."""
    try:
        claims = verify_request_user(request)
    except AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    admin = _admin()
    uid = claims["sub"]
    try:
        ratings = (
            admin.table("player_ratings")
            .select("sport_id,current_rating,peak_rating,matches_count,sports(name,icon)")
            .eq("user_id", uid)
            .execute()
        )
        history = (
            admin.table("rating_history")
            .select("*,sports(name,icon),matches(id)")
            .eq("user_id", uid)
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        return (
            jsonify(
                {
                    "ratings": ratings.data or [],
                    "history": history.data or [],
                    "disclaimer": "Ratings are provisional until several verified "
                                  "matches are recorded.",
                }
            ),
            200,
        )
    except Exception:  # noqa: BLE001
        return jsonify({"error": "Could not load ratings."}), 500


@ratings_bp.get("/player/<user_id>")
def player_ratings(user_id: str):
    """Public-safe rating summary of any player (no sensitive profile data)."""
    verify_request_user(request)  # must be signed in, but any user may view
    try:
        res = (
            _admin()
            .table("player_ratings")
            .select("sport_id,current_rating,peak_rating,matches_count,sports(name,icon)")
            .eq("user_id", user_id)
            .execute()
        )
        return jsonify({"ratings": res.data or []}), 200
    except Exception:  # noqa: BLE001
        return jsonify({"error": "Could not load ratings."}), 500
