"""Private evidence submissions and verification status."""
from uuid import UUID

from flask import Blueprint, current_app, jsonify, request

from backend.services.auth_service import AuthError, verify_request_user

verification_bp = Blueprint("verification", __name__, url_prefix="/api/verification")

BUCKET = "skill-evidence"
MAX_FILES = 3
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
METHODS = {"results", "images", "certificate", "coach"}


def _admin():
    from supabase import create_client
    from backend.config import config

    if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("Supabase service configuration is missing.")
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)


@verification_bp.get("/me")
def my_submissions():
    try:
        claims = verify_request_user(request)
    except AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    try:
        result = (
            _admin().table("skill_verification_submissions")
            .select("id,method,note,evidence_count,status,decision_note,created_at,reviewed_at")
            .eq("user_id", claims["sub"])
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        return jsonify({"submissions": result.data or []}), 200
    except Exception as exc:  # noqa: BLE001
        current_app.logger.error("Could not load verification status: %s", exc)
        return jsonify({"error": "Could not load verification status."}), 500


@verification_bp.post("/submit")
def submit_evidence():
    try:
        claims = verify_request_user(request)
    except AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400
    method = str(body.get("method") or "").strip()
    note = str(body.get("note") or "").strip()
    paths = body.get("evidence_paths")
    if method not in METHODS:
        return jsonify({"error": "Choose a valid verification source."}), 400
    if not isinstance(paths, list) or len(paths) < 1 or len(paths) > MAX_FILES:
        return jsonify({"error": "Attach between 1 and 3 evidence files."}), 400
    if len(note) > 1000:
        return jsonify({"error": "Context must be at most 1000 characters."}), 400

    for path in paths:
        if not isinstance(path, str) or not path.startswith(claims["sub"] + "/"):
            return jsonify({"error": "Evidence paths must belong to your account."}), 400
        parts = path.split("/")
        if len(parts) != 2 or "." not in parts[1]:
            return jsonify({"error": "Evidence path is invalid."}), 400
        file_id, extension = parts[1].rsplit(".", 1)
        try:
            UUID(file_id)
        except ValueError:
            return jsonify({"error": "Evidence path is invalid."}), 400
        if "." + extension.lower() not in ALLOWED_EXTENSIONS:
            return jsonify({"error": "Evidence must be a JPG, PNG, WEBP, or PDF file."}), 400
    if len(set(paths)) != len(paths):
        return jsonify({"error": "Evidence paths must be unique."}), 400

    try:
        response = (
            _admin().table("skill_verification_submissions")
            .insert({
                "user_id": claims["sub"],
                "method": method,
                "note": note or None,
                "evidence_paths": paths,
                "evidence_count": len(paths),
                "status": "pending",
            })
            .execute()
        )
        return jsonify({
            "submission": response.data[0],
            "message": "Evidence saved. Your submission is pending review.",
        }), 201
    except Exception as exc:  # noqa: BLE001
        current_app.logger.error("Could not save verification evidence: %s", exc)
        return jsonify({"error": "Could not save verification evidence."}), 500
