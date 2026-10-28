"""Authentication routes (Flask REST API).

All endpoints verify the Supabase JWT from the Authorization header.
The user id ALWAYS comes from the verified token's `sub` claim — never from
browser-supplied data.
"""
from flask import Blueprint, jsonify, request

from backend.config import config
from backend.services.auth_service import (
    AuthError,
    create_profile_for_user,
    fetch_profile,
    verify_request_user,
)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.get("/me")
def me():
    """Protected endpoint: returns the profile of the token's owner.

    Frontend calls this with `Authorization: Bearer <access_token>`.
    """
    try:
        claims = verify_request_user(request)
    except AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    user_id = claims["sub"]
    profile = fetch_profile(user_id)
    return (
        jsonify(
            {
                "user": {
                    "id": user_id,
                    "email": claims.get("email"),
                    "provider": claims.get("app_metadata", {}).get("provider", "email"),
                },
                "profile": profile,
            }
        ),
        200,
    )


@auth_bp.post("/profile")
def create_profile():
    """Server-side profile creation (service role). Called once after signup.

    Body: { "full_name": "...", "username": "..." }  (both optional)
    The user id comes from the verified token, NOT the request body.
    """
    try:
        claims = verify_request_user(request)
    except AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    body = request.get_json(silent=True) or {}
    full_name = str(body.get("full_name") or "")[:100]
    username = str(body.get("username") or full_name or claims.get("email", "player").split("@")[0])[:30]

    user_id = claims["sub"]
    existing = fetch_profile(user_id)
    if existing:
        return jsonify({"profile": existing, "created": False}), 200

    ok = create_profile_for_user(user_id, claims.get("email", ""), full_name)
    if not ok:
        return jsonify({"error": "Could not create profile"}), 500

    return jsonify({"profile": fetch_profile(user_id), "created": True}), 201


@auth_bp.put("/profile")
def update_profile():
    """Update the authenticated user's own profile row (service-role write,
    but the row is scoped to the VERIFIED token's user id — RLS rules apply
    equally, so a user can never touch another user's profile).

    Body: { username?, full_name?, city?, bio? }
    """
    try:
        claims = verify_request_user(request)
    except AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    body = request.get_json(silent=True) or {}
    updates = {}
    if "username" in body:
        username = str(body["username"]).strip()
        if not (3 <= len(username) <= 30):
            return jsonify({"error": "Username must be 3-30 characters."}), 400
        updates["username"] = username
    if "full_name" in body:
        updates["full_name"] = str(body["full_name"]).strip()[:100] or None
    if "city" in body:
        updates["city"] = str(body["city"]).strip()[:100] or None
    if "bio" in body:
        bio = str(body["bio"]).strip()
        if len(bio) > 500:
            return jsonify({"error": "Bio must be at most 500 characters."}), 400
        updates["bio"] = bio or None

    if not updates:
        return jsonify({"error": "No valid fields to update."}), 400

    try:
        from supabase import create_client

        admin = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)
        res = (
            admin.table("profiles")
            .update(updates)
            .eq("id", claims["sub"])     # scope: verified user only
            .execute()
        )
        if not res.data:
            return jsonify({"error": "Profile not found."}), 404
        return jsonify({"profile": res.data[0]}), 200
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "unique" in msg.lower():
            return jsonify({"error": "That username is already taken."}), 409
        return jsonify({"error": "Could not update profile."}), 500


@auth_bp.get("/protected-demo")
def protected_demo():
    """Minimal protected endpoint for manual testing of token verification."""
    try:
        claims = verify_request_user(request)
    except AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"message": f"Hello {claims.get('email', 'player')}!"}), 200
