"""Initial Rating Service — hybrid questionnaire-based player rating.

All scoring constants are centralized here so the system stays transparent
and configurable.

FORMULA (fully documented, see docs/QUESTIONNAIRE.md for a worked example)
==========================================================================
1. Each question has weighted options (value 1..max). The raw score of a
   question is   value_q / max_value_q   (normalised to 0..1).
2. Each question carries a configurable weight (weights sum to 1.0).
3. Weighted score = sum(weight_q * normalised_q)  -> in range 0..1.
5. Rating = direct linear map of the weighted score onto the rating span:
       rating = MIN_RATING + weighted_score * (MAX_RATING - MIN_RATING)
   i.e. score 0.0 -> 700, score 0.5 -> 1050, score 1.0 -> 1400.
   The neutral BASE_RATING (1000) remains the default rating used when no
   questionnaire exists; the clamp keeps every initial rating in range.
5. Rating = MIN_RATING + weighted_score × (MAX_RATING − MIN_RATING)
   → score 0.0 = 700, 0.5 = 1050, 1.0 = 1400. Clamp keeps it in range.

Anti-abuse: the FIRST submission per (user, sport) sets the rating. Any
resubmission is stored as a new attempt but does NOT overwrite the initial
rating — re-rating happens only through verified match results (Elo, later
stage). This prevents gaming the questionnaire.
"""
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Configurable constants
# ---------------------------------------------------------------------------
BASE_RATING = 1000          # neutral starting Elo
MIN_RATING = 700            # hard floor for an initial rating
MAX_RATING = 1400           # hard ceiling for an initial rating (provisional!)
# Half the full rating span: (1400-700)/2 = 350 points of swing in EACH
# direction from BASE_RATING. SWING/2 maps score 1.0 -> +350 (=1400 cap)
# and score 0.0 -> -350 (=700 floor); adjustment is halved because the
# midpoint NEUTRAL_SCORE=0.5 already contributes 0.
SWING = 350.0               # max +/- points the questionnaire can apply
NEUTRAL_SCORE = 0.5         # a perfectly average questionnaire => no change

# Question weights (must sum to 1.0). Verified competitive history counts
# most; self-reported skill counts least (least trustworthy signal).
WEIGHTS: Dict[str, float] = {
    "frequency":    0.25,
    "experience":   0.25,
    "competitive":  0.30,
    "self_skill":   0.10,
    "fitness":      0.10,
}

assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "Question weights must sum to 1"

# ---------------------------------------------------------------------------
# Question definitions (shared with the frontend via GET /api/questionnaire)
# Options are ordered easiest -> hardest; value is 1-based.
# ---------------------------------------------------------------------------
QUESTIONS: List[dict] = [
    {
        "id": "frequency",
        "text": "How often do you currently play this sport?",
        "options": [
            {"label": "Rarely / never played", "value": 1},
            {"label": "A few times a year", "value": 2},
            {"label": "About once a month", "value": 3},
            {"label": "Every week", "value": 4},
            {"label": "Several times a week", "value": 5},
        ],
    },
    {
        "id": "experience",
        "text": "How many years of experience do you have?",
        "options": [
            {"label": "Less than 1 year", "value": 1},
            {"label": "1–2 years", "value": 2},
            {"label": "3–5 years", "value": 3},
            {"label": "6–10 years", "value": 4},
            {"label": "More than 10 years", "value": 5},
        ],
    },
    {
        "id": "competitive",
        "text": "Have you competed at an organised level?",
        "options": [
            {"label": "Never competed", "value": 1},
            {"label": "School / college events", "value": 2},
            {"label": "Club / district level", "value": 3},
            {"label": "State or national level", "value": 4},
        ],
    },
    {
        "id": "self_skill",
        "text": "How would you rate your own skill?",
        "options": [
            {"label": "Beginner", "value": 1},
            {"label": "Casual player", "value": 2},
            {"label": "Solid club player", "value": 3},
            {"label": "Advanced", "value": 4},
        ],
    },
    {
        "id": "fitness",
        "text": "How is your general fitness for this sport?",
        "options": [
            {"label": "Low — I tire quickly", "value": 1},
            {"label": "Average", "value": 2},
            {"label": "Good", "value": 3},
            {"label": "Excellent", "value": 4},
        ],
    },
]


class ValidationError(Exception):
    """Raised when questionnaire answers are invalid."""


def get_questions() -> List[dict]:
    """Public shape sent to the frontend (correct answers are never secret,
    but we keep the payload clean)."""
    return [
        {"id": q["id"], "text": q["text"], "options": q["options"]}
        for q in QUESTIONS
    ]


def validate_answers(answers: dict) -> Dict[str, int]:
    """Validate every submitted answer against the question definitions.

    Raises ValidationError on: missing questions, unknown ids, out-of-range
    values, non-integer values, or extra/unknown keys.

    Returns {question_id: int_value}.
    """
    if not isinstance(answers, dict):
        raise ValidationError("Answers must be a JSON object.")

    expected = {q["id"] for q in QUESTIONS}
    provided = set(answers.keys())

    missing = expected - provided
    if missing:
        raise ValidationError(f"Missing answers for: {', '.join(sorted(missing))}")

    unknown = provided - expected
    if unknown:
        raise ValidationError(f"Unknown question ids: {', '.join(sorted(unknown))}")

    validated: Dict[str, int] = {}
    for q in QUESTIONS:
        raw = answers[q["id"]]
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ValidationError(f"Answer for '{q['id']}' must be an integer.")
        max_val = q["options"][-1]["value"]
        if not (1 <= raw <= max_val):
            raise ValidationError(
                f"Answer for '{q['id']}' must be between 1 and {max_val}."
            )
        validated[q["id"]] = raw

    return validated


def compute_initial_rating(answers: Dict[str, int]) -> dict:
    """Compute the provisional initial rating from validated answers.

    Returns a fully transparent breakdown for audit purposes:
    {
      "weighted_score": 0.0..1.0,
      "adjustment": int (may be negative),
      "initial_rating": int,
      "per_question": {"<id>": {"value": n, "max": n, "normalised": f, "weight": f}},
      "clamped": bool
    }
    """
    validated = validate_answers(answers)
    per_question: Dict[str, dict] = {}
    weighted_score = 0.0

    for q in QUESTIONS:
        qid = q["id"]
        value = validated[qid]
        max_val = q["options"][-1]["value"]
        normalised = value / max_val          # 0..1
        weight = WEIGHTS[qid]
        weighted_score += weight * normalised
        per_question[qid] = {
            "value": value,
            "max": max_val,
            "normalised": round(normalised, 4),
            "weight": weight,
        }

    adjustment = round(
        MIN_RATING + weighted_score * (MAX_RATING - MIN_RATING) - BASE_RATING
    )
    rating = BASE_RATING + adjustment

    clamped = not (MIN_RATING <= rating <= MAX_RATING)
    rating = max(MIN_RATING, min(MAX_RATING, rating))

    return {
        "weighted_score": round(weighted_score, 4),
        "adjustment": adjustment,
        "initial_rating": rating,
        "per_question": per_question,
        "clamped": clamped,
    }


def compute_attempt_number(existing_attempts: Optional[int]) -> int:
    """Next attempt number for the anti-abuse rule (1-based)."""
    return (existing_attempts or 0) + 1
