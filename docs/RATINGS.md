# Stage 7 — Post-Match Ratings (Elo + bounded peer feedback)

## Mathematical formula

**Elo (teams pooled by mean rating):**

```
R_A = mean(team A ratings)          R_B = mean(team B ratings)
E_A = 1 / (1 + 10^((R_B − R_A)/400))        E_B = 1 − E_A
S   = 1 win · 0.5 draw · 0 loss             (for the team)
K   = K_BASE(32)      if matches ≥ 5
    = K_PROV(48)      if matches < 5        (provisional convergence)
    = min(K + 4·(margin−1), K_MAX=64)       (margin scaling)
R_new = clamp(R_old + K·(S − E), 100, 3000)   (all players in a team move
                                               by the SAME delta)
```

**Peer-feedback adjustment — separate, bounded, testable:**

```
adj = clamp( 5 · avg_over_reviews[(sportsmanship−3)+(skill−3)], −15, +15 )
adj = 0   if fewer than 2 distinct reviews
```

Applied **only** at the next rating pass via
`feedback_adjustment_for(match, user)` (migration 006). Safeguards:
±15 cap, minimum sample of 2 reviewers, reviewers must be real match
participants, one review per (match, reviewer, reviewee) unique constraint.
**Feedback alone is NOT a measure of actual ability** — it is a small
sportsmanship/etiquette signal; the match outcome remains dominant.

## Worked numerical example

Team A = two players at **1044** each (the questionnaire example).
Team B = two players at **1100** each. A wins **3–1**.

```
E_A = 1/(1+10^((1100−1044)/400)) = 1/(1+10^0.14) = 1/2.3804 ≈ 0.4201
S   = 1 (A won)
Δ   = round(32 · (1 − 0.4201)) = round(18.56) = 19   (margin 2 → K=36 → Δ=21)
Both A players: 1044 + Δ ;  both B players: 1100 − Δ
```

With the plain K=32 (margin ignored): Δ = 19 → Team A players rise to
**1063**, Team B players fall to **1081**. Covered exactly in
`tests/test_elo_service.py::TestTeamUpdate::test_worked_example_from_docs`.

For the simple equal-team case (1000 vs 1000, 2–1): E=0.5, K=32 →
**+16 / −16** — also asserted in tests.

## Atomicity & double-processing (req. 9, 13)

`apply_match_ratings(...)` (migration 006) runs in ONE transaction:
result row (with `unique(match_id)` race guard), participant snapshot,
per-player updates verified against the caller's read rating
(`RATING_STALE` on conflict), `rating_history` rows
(`unique (user, sport, match, reason)` = second guard), skill-profile tallies,
match → `verified`, lobby → `completed`. Any failure rolls back everything —
partial updates are impossible. Users have **no write policies** on
`player_ratings`/`rating_history` (stage 2) — only this security-definer
function, callable by `service_role` only (req. 10).

## Files

- `backend/services/elo_service.py` — formula, validation, feedback rule
- `backend/routes/results.py` — result/feedback/statistics endpoints
- `backend/routes/ratings.py` — `GET /api/ratings/me`, `/player/<id>`
- `supabase/migrations/006_match_ratings.sql` — atomic RPC + feedback helper
- `tests/test_elo_service.py` — 22 unit tests
- Frontend: profile ratings display wired via `/api/ratings/me` (dashboard card)

## Testing a completed match (end to end)

1. Run migration 006 in the SQL Editor.
2. `python -m unittest tests.test_elo_service -v` — all pure-math tests pass
   with no database needed.
3. Create a lobby (Stage 6), have ≥2 users join, **Start match**
   (status → in_progress).
4. Assign teams via SQL for the demo: `update lobby_participants set
   team_side='team_a' where lobby_id='<id>' and user_id='<u1>';` etc.
5. As the host (or a participant):
   ```powershell
   $body = '{"team_a_score":3,"team_b_score":1}'
   Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:5000/api/matches/<match_id>/result" `
     -Headers @{Authorization="Bearer <host-token>"} -ContentType "application/json" -Body $body
   ```
   → 201 with `rating_changes` showing deltas; lobby → completed.
6. Submit the SAME result again → 409 *"already processed"*
   (double-processing blocked).
7. A user who didn't play submits → 403.
8. Participants POST `/api/matches/<id>/feedback` with
   `{"reviews":[{"reviewee_id":"…","skill_score":4,"sportsmanship_score":5}]}`
   → saved; self-review or non-participant → 400/403.
9. `GET /api/ratings/me` → new `current_rating` + history rows with deltas.
