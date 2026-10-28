"""Lobby discovery routes — location-based match search."""
import math

from flask import Blueprint, jsonify, request

from backend.services.auth_service import AuthError, verify_request_user
from backend.services.geo_service import (
    GeoValidationError,
    bounding_box,
    filter_lobbies_by_distance,
)

lobbies_bp = Blueprint("lobbies", __name__, url_prefix="/api/lobbies")

# Lobbies joinable only in these statuses (full/closed never offered).
JOINABLE_STATUSES = ("open",)


@lobbies_bp.get("/nearby")
def nearby():
    """Search active public lobbies near a coordinate.

    Query params:
      lat        : -90..90           (required)
      lon        : -180..180         (required)
      radius_km  : 0.5..100          (optional, default 10)
      sport_id   : uuid              (optional filter)

    Invalid coordinates/radius -> 400. Token required.
    """
    try:
        verify_request_user(request)
    except AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    try:
        lat = float(request.args.get("lat"))
        lon = float(request.args.get("lon"))
    except (TypeError, ValueError):
        return jsonify({"error": "lat and lon query parameters are required numbers."}), 400

    radius_raw = request.args.get("radius_km", "10")
    sport_id = request.args.get("sport_id") or None

    from backend.services.geo_service import validate_latitude, validate_longitude, validate_radius

    try:
        lat = validate_latitude(lat)
        lon = validate_longitude(lon)
        radius_km = validate_radius(radius_raw)
    except GeoValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    if sport_id is not None and len(sport_id) != 36:
        return jsonify({"error": "sport_id must be a valid id."}), 400

    # ---- Fetch candidate lobbies from Supabase -----------------------------
    try:
        from supabase import create_client
        from backend.config import config

        admin = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)

        box = bounding_box(lat, lon, radius_km)

        query = (
            admin.table("lobbies")
            .select(
                "id,title,description,latitude,longitude,scheduled_at,team_size,"
                "min_players,max_players,status,visibility,"
                "sports(id,code,name,icon),"
                "grounds(name,city),"
                "lobby_participants(user_id)"
            )
            .eq("visibility", "public")
            .in_("status", ["open", "full", "in_progress"])
            .gte("scheduled_at", "now()")              # upcoming only
            .gte("latitude", box["min_lat"]).lte("latitude", box["max_lat"])
            .gte("longitude", box["min_lon"]).lte("longitude", box["max_lon"])
        )
        if sport_id:
            query = query.eq("sport_id", sport_id)

        res = query.execute()
        rows = res.data or []
    except Exception:  # noqa: BLE001
        return jsonify({"error": "Could not search lobbies."}), 500

    # ---- Shape rows: available places, joinable flag -----------------------
    candidates = []
    for row in rows:
        participants = row.pop("lobby_participants", []) or []
        joined = len(participants)
        max_players = row.get("max_players") or 0
        row["players_joined"] = joined
        row["places_available"] = max(0, max_players - joined)
        row["joinable"] = (
            row["status"] in JOINABLE_STATUSES and row["places_available"] > 0
        )
        ground = row.pop("grounds", None)
        row["ground_name"] = ground["name"] if ground else "Custom location"
        sport = row.pop("sports", None)
        row["sport"] = {"id": sport["id"], "name": sport["name"], "icon": sport["icon"]} if sport else None
        candidates.append(row)

    # ---- Exact Haversine filter + sort -------------------------------------
    matches = filter_lobbies_by_distance(candidates, lat, lon, radius_km)

    return (
        jsonify(
            {
                "origin": {"lat": lat, "lon": lon},
                "radius_km": radius_km,
                "count": len(matches),
                "lobbies": [
                    {
                        "id": lb["id"],
                        "title": lb["title"],
                        "description": lb.get("description"),
                        "sport": lb["sport"],
                        "ground_name": lb["ground_name"],
                        "distance_km": dist,
                        "scheduled_at": lb["scheduled_at"],
                        "status": lb["status"],
                        "team_size": lb["team_size"],
                        "players_joined": lb["players_joined"],
                        "places_available": lb["places_available"],
                        "joinable": lb["joinable"],
                    }
                    for lb, dist in matches
                ],
                "note": "Distances computed with the Haversine formula from "
                        "your selected point to each lobby's stored coordinates.",
            }
        ),
        200,
    )
