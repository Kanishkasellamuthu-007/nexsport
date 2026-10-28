"""Elo rating service — the authoritative post-match rating engine.

MATHEMATICAL FORMULA
====================
Standard Elo (two teams treated as pooled entities):

    R_home = mean(rating of team A players)
    R_away = mean(rating of team B players)
    E_A = 1 / (1 + 10 ** ((R_away - R_A) / 400))        # expected score
    E_B = 1 - E_A
    S   = 1 (win) / 0.5 (draw) / 0 (loss)               # actual score

    K-factor scaled by goal/point margin:
        K_i = K_BASE + K_MARGIN_SCALE * (abs(margin) - 1)   (margin >= 1)
        capped at K_MAX

    R_new = R_old + K * (S - E)      # per player, same team -> same delta

Guards:  provisional players (fewer than PROVISIONAL_MATCHES matches) use
K_PROVISIONAL so early ratings converge quickly.  Every rating is clamped to
[RATING_FLOOR, RATING_CEILING].

PEER FEEDBACK ADJUSTMENT (clear, bounded, testable rule)
========================================================
Feedback is a SEPARATE, bounded adjustment — never mixed into the Elo
expectation itself:

    adj_i = FEEDBACK_GAIN * (avg_sportsmanship - 3) + FEEDBACK_GAIN * (avg_skill - 3)

Requirements before ANY adjustment is applied:
  * MIN_FEEDBACK_REVIEWS distinct reviewers (anti-noise minimum sample)
  * both 1..5 scores present, review made by a real match participant
  * feedback EXISTS only for this match; it is applied exactly once
    (flagged on match_results.ratings_applied)

Collusion safeguards:
  * MAX_FEEDBACK_ADJUSTMENT caps the total adjustment (±15 points)
  * only reviewers who actually played the match count (enforced by
    match_participants FK data + RLS policy from stage 2)
  * one review per (match, reviewer, reviewee) — unique constraint prevents
    review flooding
  * we never claim feedback alone measures real ability: it is a small
    sportsmanship/etiquette nudge on top of the match outcome.

Note: feedback is submitted AFTER the Elo update, so its adjustment is
applied lazily at the next match's rating pass (or via a recompute hook).
This keeps the match-update atomic and simple; see docs/RATINGS.md.
"""
import math
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Configurable Elo constants
# ---------------------------------------------------------------------------
K_BASE = 32.0               # standard K-factor for established players
K_PROVISIONAL = 48.0        # faster convergence for new players
K_MARGIN_SCALE = 4.0        # extra K per goal of margin
K_MAX = 64.0                # upper bound on K
PROVISIONAL_MATCHES = 5     # below this match count -> K_PROVISIONAL
RATING_FLOOR = 100
RATING_CEILING = 3000
ELO_SCALE = 400.0           # standard Elo divisor

# ---------------------------------------------------------------------------
# Peer feedback adjustment constants (bounded)
# ---------------------------------------------------------------------------
FEEDBACK_GAIN = 5.0                 # points per full star away from neutral 3
MAX_FEEDBACK_ADJUSTMENT = 15.0      # hard cap on |adjustment|
MIN_FEEDBACK_REVIEWS = 2            # minimum distinct reviewers


class ResultValidationError(Exception):
    """Invalid match result payload."""


def expected_score(rating_a: float, rating_b: float) -> float:
    """Standard Elo expected score for A: 1 / (1 + 10^((Rb-Ra)/400))."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / ELO_SCALE))


def actual_score(goals_a: int, goals_b: int) -> float:
    if goals_a > goals_b:
        return 1.0
    if goals_a < goals_b:
        return 0.0
    return 0.5


def k_factor(matches_played: int, margin: int) -> float:
    """K with provisional boost and margin scaling, capped at K_MAX."""
    base = K_PROVISIONAL if matches_played < PROVISIONAL_MATCHES else K_BASE
    if margin >= 1:
        base = min(base + K_MARGIN_SCALE * (margin - 1), K_MAX)
    return min(base, K_MAX)


def compute_team_update(
    team_a: List[dict],   # [{"user_id":..., "rating": int, "matches": int}, ...]
    team_b: List[dict],
    goals_a: int,
    goals_b: int,
) -> Dict[str, dict]:
    """Compute per-player rating updates for one match.

    Returns {user_id: {"old": int, "new": int, "delta": int}} — teams share
    the same mean-based delta, so ratings move as coherent groups.
    """
    if not team_a or not team_b:
        raise ResultValidationError("Both teams must have at least one player.")

    mean_a = sum(p["rating"] for p in team_a) / len(team_a)
    mean_b = sum(p["rating"] for p in team_b) / len(team_b)

    e_a = expected_score(mean_a, mean_b)
    s_a = actual_score(goals_a, goals_b)
    margin = abs(goals_a - goals_b)

    # K from the match experience of each team (conservative: take the min,
    # i.e. the least-experienced team governs K); margin is goal difference.
    matches_a = min(p["matches"] for p in team_a)
    matches_b = min(p["matches"] for p in team_b)
    k = min(k_factor(matches_a, margin), k_factor(matches_b, margin))

    # Delta for TEAM A; team B gets the exact opposite.
    delta = round(k * (s_a - e_a))
    out = {}
    for p in team_a:
        old = p["rating"]
        new = int(max(RATING_FLOOR, min(RATING_CEILING, old + delta)))
        out[p["user_id"]] = {"old": old, "new": new, "delta": new - old}
    for p in team_b:
        old = p["rating"]
        new = int(max(RATING_FLOOR, min(RATING_CEILING, old - delta)))
        out[p["user_id"]] = {"old": old, "new": new, "delta": new - old}
    return out


def feedback_adjustment(reviews: List[dict]) -> float:
    """Bounded feedback adjustment for one player.

    reviews: [{"skill_score": 1..5, "sportsmanship_score": 1..5}, ...]
    Returns 0.0 when the minimum sample is not met.  Clamped to
    ±MAX_FEEDBACK_ADJUSTMENT.  NOT a measure of true ability — a nudge only.
    """
    if len(reviews) < MIN_FEEDBACK_REVIEWS:
        return 0.0
    total = 0.0
    for r in reviews:
        total += (r["sportsmanship_score"] - 3) + (r["skill_score"] - 3)
    avg_delta = total / len(reviews)
    adj = FEEDBACK_GAIN * avg_delta
    return max(-MAX_FEEDBACK_ADJUSTMENT, min(MAX_FEEDBACK_ADJUSTMENT, round(adj, 1)))


def validate_result_payload(data: dict) -> dict:
    """Validate the result submission before anything is persisted."""
    if not isinstance(data, dict):
        raise ResultValidationError("Body must be a JSON object.")

    try:
        ga = int(data["team_a_score"])
        gb = int(data["team_b_score"])
    except (KeyError, TypeError, ValueError):
        raise ResultValidationError("team_a_score and team_b_score are required integers.")
    if ga < 0 or gb < 0:
        raise ResultValidationError("Scores cannot be negative.")
    if max(ga, gb) > 99:
        raise ResultValidationError("Scores look unrealistic (>99).")

    winner = data.get("winner_side")
    if winner not in ("team_a", "team_b", "unassigned"):
        # derive from score if absent
        if ga > gb:
            winner = "team_a"
        elif gb > ga:
            winner = "team_b"
        else:
            winner = "unassigned"

    stats = data.get("statistics") or []
    if not isinstance(stats, list):
        raise ResultValidationError("statistics must be a list.")
    for s in stats:
        if not isinstance(s, dict) or "user_id" not in s:
            raise ResultValidationError("Each statistic needs a user_id.")
        for field in ("goals", "assists"):
            if field in s and (not isinstance(s[field], int) or s[field] < 0):
                raise ResultValidationError(f"{field} must be a non-negative integer.")

    return {
        "team_a_score": ga,
        "team_b_score": gb,
        "winner_side": winner,
        "statistics": stats,
    }


# ---------------------------------------------------------------------------
# Database application (service role; atomic per match)
# ---------------------------------------------------------------------------
def apply_ratings(match_id: str, team_a: List[dict], team_b: List[dict],
                  goals_a: int, goals_b: int) -> Dict[str, dict]:
    """Persist: match_results, match_participants, player_ratings,
    rating_history, player_skill_profiles, matches.status — all within one
    postgrest RPC transaction (see migration 006 apply_match_ratings).
    Idempotent: a second call for the same match is refused by a unique
    constraint on rating_history (user, sport, match, 'match_result').
    """
    from supabase import create_client
    from backend.config import config

    admin = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)
    updates = compute_team_update(team_a, team_b, goals_a, goals_b)

    payload = {
        "p_match_id": match_id,
        "p_goals_a": goals_a,
        "p_goals_b": goals_b,
        "p_updates": [
            {"user_id": uid, "old": v["old"], "new": v["new"], "delta": v["delta"]}
            for uid, v in updates.items()
        ],
    }
    res = admin.rpc("apply_match_ratings", payload).execute()
    return {"updates": updates, "db": res.data}
