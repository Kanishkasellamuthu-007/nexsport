"""Sports catalogue endpoint."""
from flask import Blueprint, jsonify

from supabase import create_client

from backend.config import config

sports_bp = Blueprint("sports", __name__, url_prefix="/api")


@sports_bp.get("/sports")
def list_sports():
    """Public list of active sports (used by the questionnaire dropdown)."""
    try:
        admin = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)
        res = (
            admin.table("sports")
            .select("id,code,name,icon,team_size,min_players,max_players")
            .eq("is_active", True)
            .order("name")
            .execute()
        )
        return jsonify({"sports": res.data}), 200
    except Exception:  # noqa: BLE001
        return jsonify({"error": "Could not load sports."}), 500

@sports_bp.get("/grounds")
def list_grounds():
    """Public list of known grounds (used by the create-lobby picker)."""
    try:
        admin = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)
        res = (
            admin.table("grounds")
            .select("id,name,city,latitude,longitude")
            .eq("is_active", True)
            .order("name")
            .execute()
        )
        return jsonify({"grounds": res.data}), 200
    except Exception:  # noqa: BLE001
        return jsonify({"error": "Could not load grounds."}), 500
