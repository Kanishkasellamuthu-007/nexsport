"""Sports catalogue endpoint."""
from flask import Blueprint, jsonify

from backend.config import config

sports_bp = Blueprint("sports", __name__, url_prefix="/api")

# ── Demo fallback data ───────────────────────────────────────────
DEMO_SPORTS = [
    {"id": 1, "code": "football",    "name": "Football",     "icon": "⚽", "team_size": 11, "min_players": 6,  "max_players": 22},
    {"id": 2, "code": "cricket",     "name": "Cricket",      "icon": "🏏", "team_size": 11, "min_players": 6,  "max_players": 22},
    {"id": 3, "code": "basketball",  "name": "Basketball",   "icon": "🏀", "team_size": 5,  "min_players": 4,  "max_players": 10},
    {"id": 4, "code": "badminton",   "name": "Badminton",    "icon": "🏸", "team_size": 1,  "min_players": 2,  "max_players": 4},
    {"id": 5, "code": "tennis",      "name": "Tennis",       "icon": "🎾", "team_size": 1,  "min_players": 2,  "max_players": 4},
    {"id": 6, "code": "volleyball",  "name": "Volleyball",   "icon": "🏐", "team_size": 6,  "min_players": 4,  "max_players": 12},
    {"id": 7, "code": "tabletennis", "name": "Table Tennis",  "icon": "🏓", "team_size": 1,  "min_players": 2,  "max_players": 4},
    {"id": 8, "code": "swimming",    "name": "Swimming",     "icon": "🏊", "team_size": 1,  "min_players": 2,  "max_players": 8},
    {"id": 9, "code": "running",     "name": "Running",      "icon": "🏃", "team_size": 1,  "min_players": 2,  "max_players": 20},
]

DEMO_GROUNDS = [
    {"id": 1, "name": "Chennai Sports Arena",      "city": "Chennai",  "latitude": 13.0827, "longitude": 80.2707},
    {"id": 2, "name": "Marina Beach Ground",        "city": "Chennai",  "latitude": 13.0500, "longitude": 80.2824},
    {"id": 3, "name": "Nungambakkam Tennis Club",   "city": "Chennai",  "latitude": 13.0569, "longitude": 80.2425},
    {"id": 4, "name": "ECR Cricket Ground",          "city": "Chennai",  "latitude": 12.9516, "longitude": 80.2547},
    {"id": 5, "name": "Velachery Badminton Hub",     "city": "Chennai",  "latitude": 12.9815, "longitude": 80.2180},
    {"id": 6, "name": "Besant Nagar Football Turf",  "city": "Chennai",  "latitude": 13.0002, "longitude": 80.2660},
]


@sports_bp.get("/sports")
def list_sports():
    """Public list of active sports (used by the questionnaire dropdown)."""
    try:
        from supabase import create_client
        admin = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)
        res = (
            admin.table("sports")
            .select("id,code,name,icon,team_size,min_players,max_players")
            .eq("is_active", True)
            .order("name")
            .execute()
        )
        if res.data:
            return jsonify({"sports": res.data}), 200
    except Exception:  # noqa: BLE001
        pass
    # Fallback to demo sports when Supabase is unavailable
    return jsonify({"sports": DEMO_SPORTS}), 200

@sports_bp.get("/grounds")
def list_grounds():
    """Public list of known grounds (used by the create-lobby picker)."""
    try:
        from supabase import create_client
        admin = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)
        res = (
            admin.table("grounds")
            .select("id,name,city,latitude,longitude")
            .eq("is_active", True)
            .order("name")
            .execute()
        )
        if res.data:
            return jsonify({"grounds": res.data}), 200
    except Exception:  # noqa: BLE001
        pass
    # Fallback to demo grounds when Supabase is unavailable
    return jsonify({"grounds": DEMO_GROUNDS}), 200
