"""Improved Greedy Zig-Zag Split Algorithm — team balancing module.

Pure functions only: no I/O, no rating mutation, fully deterministic.

ALGORITHM (documented, deterministic)
=====================================
Phase 1 — Baseline zig-zag (snake draft):
    1. Sort players by rating DESC, tie-break by user_id ASC (deterministic).
    2. Deal players alternately to Team A / Team B ("snake"): the classic
       zig-zag keeps each team's successive picks close in rating, which
       already balances aggregate strength well.

Phase 2 — Improvement step (bounded greedy swap):
    3. Compute |sum(A) − sum(B)|.
    4. While an improvement is possible (bounded passes to guarantee
       termination), consider all A×B swap pairs; find the pair whose swap
       reduces the difference the most while keeping BOTH teams valid.
       Perform the best swap if it strictly improves; otherwise stop.
    5. Termination: each pass either strictly reduces the difference or we
       stop — and the difference is a non-negative integer that decreases,
       so the loop provably terminates (worst case: reaches a local minimum).

HONESTY NOTE: this is a greedy local-search heuristic. It is NOT guaranteed
to find the globally optimal partition (balanced-partition is NP-hard);
it reliably produces near-optimal, fair teams in practice, and the tests
quantify the improvement over the plain zig-zag baseline.
"""
from typing import Dict, List, Tuple


class TeamSplitError(Exception):
    """Raised for invalid inputs to the team splitter."""


def _validate(players: List[dict], expected_count: int) -> List[Tuple[str, int]]:
    """Validate and normalise input; returns sorted [(user_id, rating)]."""
    if not isinstance(players, list) or not players:
        raise TeamSplitError("Players list must be a non-empty list.")
    if expected_count is not None and len(players) != expected_count:
        raise TeamSplitError(
            f"Expected {expected_count} players, got {len(players)}."
        )
    if len(players) % 2 != 0:
        raise TeamSplitError("Equal team sizes require an even number of players.")

    seen = set()
    normalised = []
    for p in players:
        if not isinstance(p, dict) or "user_id" not in p or "rating" not in p:
            raise TeamSplitError("Each player needs user_id and rating.")
        uid = str(p["user_id"])
        if not uid:
            raise TeamSplitError("user_id cannot be empty.")
        if uid in seen:
            raise TeamSplitError(f"Duplicate player id: {uid}")
        seen.add(uid)
        try:
            rating = int(p["rating"])
        except (TypeError, ValueError):
            raise TeamSplitError(f"Rating for {uid} must be an integer.")
        if rating < 0:
            raise TeamSplitError(f"Rating for {uid} cannot be negative.")
        normalised.append((uid, rating))

    # Deterministic sort: rating DESC, then user_id ASC for ties.
    normalised.sort(key=lambda t: (-t[1], t[0]))
    return normalised


def zigzag_baseline(players: List[dict], expected_count: int = None) -> dict:
    """Plain snake-draft split — the comparison baseline."""
    sorted_players = _validate(players, expected_count)

    team_a: List[str] = []
    team_b: List[str] = []

    for i, (uid, _r) in enumerate(sorted_players):
        if i % 2 == 0:
            team_a.append(uid)
        else:
            team_b.append(uid)

    return _result(sorted_players, team_a, team_b)


def improved_zigzag_split(players: List[dict], expected_count: int = None,
                          max_passes: int = 50) -> dict:
    """Improved zig-zag: snake draft + bounded greedy swap improvement."""
    sorted_players = _validate(players, expected_count)

    # ---- Phase 1: zig-zag (snake) draft ----
    team_a: List[str] = []
    team_b: List[str] = []
    for i, (uid, _r) in enumerate(sorted_players):
        if i % 2 == 0:
            team_a.append(uid)
        else:
            team_b.append(uid)

    ratings = dict(sorted_players)
    signed = sum(ratings[u] for u in team_a) - sum(ratings[u] for u in team_b)
    diff = abs(signed)

    # ---- Phase 2: bounded greedy swap improvement ----
    improved_any = False
    for _ in range(max_passes):
        gain_pair = None
        best_gain = 0
        for uid_a in team_a:
            for uid_b in team_b:
                # swap a (in A) with b (in B): signed changes by -2*(a-b)
                new_signed = signed - 2 * (ratings[uid_a] - ratings[uid_b])
                gain = diff - abs(new_signed)
                if gain > best_gain:
                    best_gain = gain
                    gain_pair = (uid_a, uid_b)
        if not gain_pair:
            break  # local minimum reached — no swap improves the balance
        a_idx, b_idx = team_a.index(gain_pair[0]), team_b.index(gain_pair[1])
        team_a[a_idx], team_b[b_idx] = team_b[b_idx], team_a[a_idx]
        signed = signed - 2 * (ratings[gain_pair[0]] - ratings[gain_pair[1]])
        diff = abs(signed)
        improved_any = True

    return _result(sorted_players, team_a, team_b, improved_any)


def _result(sorted_players: List[Tuple[str, int]], team_a: List[str],
            team_b: List[str], improved: bool = False) -> dict:
    ratings = dict(sorted_players)
    total_a = sum(ratings[u] for u in team_a)
    total_b = sum(ratings[u] for u in team_b)

    # deterministic output ordering
    team_a.sort()
    team_b.sort()

    return {
        "team_a": [
            {"user_id": u, "rating": ratings[u]} for u in team_a
        ],
        "team_b": [
            {"user_id": u, "rating": ratings[u]} for u in team_b
        ],
        "team_a_total": total_a,
        "team_b_total": total_b,
        "team_a_average": round(total_a / len(team_a), 1),
        "team_b_average": round(total_b / len(team_b), 1),
        "rating_difference": abs(total_a - total_b),
        "team_size": len(team_a),
        "improved": improved,
    }
