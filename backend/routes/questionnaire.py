"""Questionnaire + initial rating routes (token-verified)."""
from flask import Blueprint, jsonify, request

from backend.services.auth_service import AuthError, verify_request_user
from backend.services import initial_rating_service as irs
from backend.services.initial_rating_service import ValidationError

questionnaire_bp = Blueprint("questionnaire", __name__, url_prefix="/api/questionnaire")


@questionnaire_bp.get("/questions")
def questions():
    """Public question list (sports-agnostic template, attempt 1)."""
    return jsonify({"questions": irs.get_questions()}), 200


@questionnaire_bp.post("/submit")
def submit():
    """Submit answers for ONE sport. Token-verified.

    Body: { "sport_id": "<uuid>", "answers": {"frequency": 3, ...} }

    Anti-abuse rules enforced server-side:
      * the first attempt stores the initial rating,
      * resubmissions are recorded but NEVER overwrite the initial rating.
    """
    try:
        claims = verify_request_user(request)
    except AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    body = request.get_json(silent=True) or {}
    sport_id = str(body.get("sport_id") or "")
    if len(sport_id) != 36:
        return jsonify({"error": "A valid sport_id is required."}), 400

    try:
        breakdown = irs.compute_initial_rating(body.get("answers") or {})
    except ValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    # --- Supabase persistence (service role, server-side only) --------------
    try:
        from supabase import create_client
        from backend.config import config

        admin = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)
        user_id = claims["sub"]

        # How many attempts exist already for this user+sport?
        prev = (
            admin.table("questionnaire_responses")
            .select("attempt_no")
            .eq("user_id", user_id)
            .eq("sport_id", sport_id)
            .order("attempt_no", desc=True)
            .limit(1)
            .execute()
        )
        prev_rows = prev.data or []
        existing_attempts = prev_rows[0]["attempt_no"] if prev_rows else 0
        attempt_no = irs.compute_attempt_number(existing_attempts)

        # Store each answer.
        rows = [
            {
                "user_id": user_id,
                "question_id": None,  # replaced with the template uuid below
                "sport_id": sport_id,
                "attempt_no": attempt_no,
                "response": {"id": q["id"], "value": breakdown["per_question"][q["id"]]["value"]},
            }
            for q in irs.QUESTIONS
        ]

        # Resolve real question uuids from the seeded template (sport_id NULL).
        qrows = (
            admin.table("questionnaire_questions")
            .select("id,question_order")
            .is_("sport_id", "null")
            .order("question_order")
            .execute()
        )
        order_to_uuid = {r["question_order"]: r["id"] for r in (qrows.data or [])}

        valid_rows = []
        for idx, row in enumerate(rows):
            uuid = order_to_uuid.get(idx + 1)
            if uuid:
                row["question_id"] = uuid
                valid_rows.append(row)

        if valid_rows:
            admin.table("questionnaire_responses").insert(valid_rows).execute()

        # First attempt only: write the authoritative initial rating.
        is_first = attempt_no == 1
        if is_first:
            admin.table("initial_ratings").insert(
                {
                    "user_id": user_id,
                    "sport_id": sport_id,
                    "attempt_no": attempt_no,
                    "rating": breakdown["initial_rating"],
                    "computed_from": {
                        "answers": body.get("answers"),
                        "weighted_score": breakdown["weighted_score"],
                        "adjustment": breakdown["adjustment"],
                    },
                }
            ).execute()
            admin.table("player_ratings").upsert(
                {
                    "user_id": user_id,
                    "sport_id": sport_id,
                    "current_rating": breakdown["initial_rating"],
                    "peak_rating": breakdown["initial_rating"],
                }
            ).execute()
            admin.table("player_skill_profiles").upsert(
                {
                    "user_id": user_id,
                    "sport_id": sport_id,
                    "questionnaire_completed": True,
                    "cached_rating": breakdown["initial_rating"],
                }
            ).execute()

        return (
            jsonify(
                {
                    "attempt_no": attempt_no,
                    "is_first_attempt": is_first,
                    "provisional_rating": breakdown["initial_rating"],
                    "breakdown": breakdown,
                    "notice": (
                        "Your provisional rating is set. It is an estimate from your "
                        "answers, not a verified skill measurement — it will be "
                        "refined by your actual match results."
                        if is_first
                        else "Recorded. Resubmissions do not change your initial "
                        "rating; verified match results will adjust it."
                    ),
                }
            ),
            201,
        )

    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "unique" in msg.lower() or "duplicate" in msg.lower():
            return jsonify({"error": "Questionnaire already submitted for this sport."}), 409
        return jsonify({"error": "Could not save questionnaire: " + msg}), 500
