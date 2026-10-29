"""
NexSport backend - Flask application entry point.

This file only creates and configures the Flask app.
Routes live in backend/routes/, services in backend/services/, etc.
"""
import os

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS


def create_app() -> Flask:
    """Application factory pattern: builds and configures the Flask app."""
    app = Flask(__name__)

    # Basic config read from environment variables (never hardcode secrets).
    app.config["JSON_SORT_KEYS"] = False

    # Allow the local frontend (and future Vercel/Capacitor origins) to call
    # the API. The list can be extended later via the CORS_ORIGINS env var.
    allowed_origins = os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000",
    ).split(",")
    CORS(app, origins=allowed_origins)

    # Register route blueprints
    from backend.routes.auth import auth_bp
    from backend.routes.health import health_bp
    from backend.routes.lobbies import lobbies_bp
    from backend.routes.lobby_management import lobbies_mgmt_bp
    from backend.routes.questionnaire import questionnaire_bp
    from backend.routes.ratings import ratings_bp
    from backend.routes.results import results_bp
    from backend.routes.sports import sports_bp
    from backend.routes.teams import teams_bp
    from backend.routes.chat import chat_bp
    from backend.routes.verification import verification_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(questionnaire_bp)
    app.register_blueprint(sports_bp)
    app.register_blueprint(lobbies_bp)
    app.register_blueprint(lobbies_mgmt_bp)
    app.register_blueprint(results_bp)
    app.register_blueprint(ratings_bp)
    app.register_blueprint(teams_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(verification_bp)

    frontend_dir = os.path.abspath(os.path.join(app.root_path, "..", "frontend"))

    @app.get("/")
    def index():
        return send_from_directory(frontend_dir, "index.html")

    @app.get("/<path:asset_path>")
    def frontend_asset(asset_path: str):
        return send_from_directory(frontend_dir, asset_path)

    # Global error handlers -> always return JSON with proper status codes.
    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return jsonify({"error": "Method not allowed"}), 405

    @app.errorhandler(500)
    def internal_error(_error):
        return jsonify({"error": "Internal server error"}), 500

    return app


# Single app instance. Used both by `flask run` / `python run.py` locally and
# by Vercel when deploying the Flask backend.
app = create_app()


if __name__ == "__main__":
    # Local development server only. Vercel uses its own WSGI runner.
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("FLASK_PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
    )
