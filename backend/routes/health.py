"""Health and browser configuration endpoints."""
import json

from flask import Blueprint, Response, jsonify

from backend.__version__ import __version__
from backend.config import config

health_bp = Blueprint("health", __name__, url_prefix="/api")


@health_bp.get("/health")
def health():
    """GET /api/health -> simple liveness check with app metadata."""
    return (
        jsonify(
            {
                "status": "ok",
                "app": "NexSport",
                "version": __version__,
                "message": "NexSport API is running",
            }
        ),
        200,
    )


@health_bp.get("/config.js")
def frontend_config():
    """Return browser-safe Supabase settings at runtime.

    The anon/publishable key is intentionally public. The service-role key is
    never read or emitted by this endpoint.
    """
    missing = [
        name
        for name, value in (
            ("SUPABASE_URL", config.SUPABASE_URL),
            ("SUPABASE_ANON_KEY", config.SUPABASE_ANON_KEY),
        )
        if not value
    ]
    if missing:
        script = (
            "throw new Error('Missing NexSport browser configuration: "
            + ", ".join(missing)
            + "');"
        )
        return Response(script, status=500, mimetype="application/javascript")

    script = (
        "window.NEXSPORT_SUPABASE_URL = "
        + json.dumps(config.SUPABASE_URL)
        + ";\nwindow.NEXSPORT_SUPABASE_ANON_KEY = "
        + json.dumps(config.SUPABASE_ANON_KEY)
        + ";\n"
        "window.supabaseClient = supabase.createClient(\n"
        "  window.NEXSPORT_SUPABASE_URL,\n"
        "  window.NEXSPORT_SUPABASE_ANON_KEY,\n"
        "  {auth: {persistSession: true, autoRefreshToken: true, detectSessionInUrl: false}}\n"
        ");\n"
    )
    return Response(script, mimetype="application/javascript")
