"""Player rating endpoints — display current ratings & history."""
from flask import Blueprint, jsonify, request

from backend.services.auth_service import AuthError, DEMO_USER_ID, verify_request_user

ratings_bp = Blueprint("ratings", __name__, url_prefix="/api/ratings")

# ── Demo fallback data ───────────────────────────────────────────
DEMO_RATINGS = [
    {
        "sport_id": 1,
        "current_rating": 1347,
        "peak_rating": 1410,
        "matches_count": 24,
        "sports": {"name": "Football", "icon": "⚽"},
    },
    {
        "sport_id": 2,
        "current_rating": 1280,
        "peak_rating": 1305,
        "matches_count": 11,
        "sports": {"name": "Cricket", "icon": "🏏"},
    },
    {
        "sport_id": 3,
        "current_rating": 1190,
        "peak_rating": 1220,
        "matches_count": 6,
        "sports": {"name": "Basketball", "icon": "🏀"},
    },
]

DEMO_HISTORY = [
    {"id": 1, "sport_id": 1, "old_rating": 1330, "new_rating": 1347, "sports": {"name": "Football", "icon": "⚽"}, "matches": {"id": "m1"}, "created_at": "2026-10-28T18:00:00Z"},
    {"id": 2, "sport_id": 1, "old_rating": 1310, "new_rating": 1330, "sports": {"name": "Football", "icon": "⚽"}, "matches": {"id": "m2"}, "created_at": "2026-10-25T14:00:00Z"},
    {"id": 3, "sport_id": 2, "old_rating": 1260, "new_rating": 1280, "sports": {"name": "Cricket", "icon": "🏏"}, "matches": {"id": "m3"}, "created_at": "2026-10-22T10:00:00Z"},
    {"id": 4, "sport_id": 1, "old_rating": 1290, "new_rating": 1310, "sports": {"name": "Football", "icon": "⚽"}, "matches": {"id": "m4"}, "created_at": "2026-10-20T16:00:00Z"},
    {"id": 5, "sport_id": 3, "old_rating": 1170, "new_rating": 1190, "sports": {"name": "Basketball", "icon": "🏀"}, "matches": {"id": "m5"}, "created_at": "2026-10-18T11:00:00Z"},
]


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

    uid = claims["sub"]

    # If demo user, return demo data directly
    if uid == DEMO_USER_ID:
        return jsonify({
            "ratings": DEMO_RATINGS,
            "history": DEMO_HISTORY,
            "disclaimer": "Ratings are provisional until several verified matches are recorded.",
        }), 200

    try:
        admin = _admin()
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
        # Fallback to demo data on any DB error
        return jsonify({
            "ratings": DEMO_RATINGS,
            "history": DEMO_HISTORY,
            "disclaimer": "Ratings are provisional (demo data — database unavailable).",
        }), 200


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
