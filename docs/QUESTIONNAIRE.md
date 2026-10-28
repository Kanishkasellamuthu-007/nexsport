# Stage 4 — Skill Questionnaire & Initial Rating

## Scoring formula (transparent & configurable)

All constants live in `backend/services/initial_rating_service.py`:

| Constant | Value | Meaning |
|---|---|---|
| `BASE_RATING` | 1000 | neutral starting Elo |
| `MIN_RATING` / `MAX_RATING` | 700 / 1400 | hard clamp — no extreme initial ratings |
| `MAX_ADJUSTMENT` | 350 | max ± points the questionnaire can move you |
| `NEUTRAL_SCORE` | 0.5 | average answers ⇒ no adjustment |

**Weights** (sum = 1.0): frequency 0.25 · experience 0.25 · competitive 0.30 ·
self_skill 0.10 · fitness 0.10. Competitive history counts most (verified-ish);
self-reported skill counts least (least trustworthy).

**Steps:**
1. Normalise each answer: `value_q / max_value_q` → 0..1.
2. `weighted_score = Σ weight_q × normalised_q`.
3. `adjustment = (weighted_score − 0.5) × 350`, rounded.
4. `initial_rating = clamp(1000 + adjustment, 700, 1400)`.

### Worked example

Player answers: frequency 4/5, experience 3/5, competitive 2/4,
self_skill 2/4, fitness 3/4.

| Question | normalised | weight | contribution |
|---|---|---|---|
| frequency | 4/5 = 0.80 | 0.25 | 0.2000 |
| experience | 3/5 = 0.60 | 0.25 | 0.1500 |
| competitive | 2/4 = 0.50 | 0.30 | 0.1500 |
| self_skill | 2/4 = 0.50 | 0.10 | 0.0500 |
| fitness | 3/4 = 0.75 | 0.10 | 0.0750 |
| **weighted_score** | | | **0.6250** |

`adjustment = (0.625 − 0.5) × 350 = 43.75 → 44`
`initial_rating = 1000 + 44 = 1044` ✔ (within 700–1400, not clamped)

## Provisional estimates — important disclaimer

Questionnaire ratings are **self-reported estimates, not verified skill
measurements**. The UI, API response and database notice all state this.
Real refinement happens only through actual match results (Elo, next stage).

## Anti-abuse rules

- The **first** submission per (user, sport) sets the rating.
- Resubmissions are stored (audit trail via `attempt_no`) but **never** change
  `initial_ratings`, `player_ratings`, or `player_skill_profiles`.
- The DB `unique (user_id, sport_id, attempt_no)` on `initial_ratings` blocks
  duplicate first-attempt writes even under race conditions.
- Validation rejects unknown ids, out-of-range/non-integer values — no hand-crafted payloads.

## New files

- `backend/services/initial_rating_service.py` — formula + validation (pure Python, no I/O)
- `backend/routes/questionnaire.py` — `GET /api/questionnaire/questions`, `POST /api/questionnaire/submit`
- `backend/routes/sports.py` — `GET /api/sports`
- `frontend/questionnaire.html` + `frontend/js/pages/questionnaire.js` — responsive questionnaire
- `tests/test_initial_rating.py` — 12 unit tests

## Testing instructions

### 1. Unit tests (no database needed)

```powershell
.\.venv\Scripts\Activate.ps1
python -m unittest tests.test_initial_rating -v
```

Expected: all tests pass, including the worked example (1044), boundary
clamping (all-min → 700, all-max → 1400), and validation rejection cases.

### 2. API tests (Supabase must be configured, migrations run, logged-in token)

```powershell
# questions (public)
Invoke-RestMethod http://127.0.0.1:5000/api/questionnaire/questions

# sports (public)
Invoke-RestMethod http://127.0.0.1:5000/api/sports

# submit — replace <TOKEN> and <SPORT_ID>
$body = '{"sport_id":"<SPORT_ID>","answers":{"frequency":4,"experience":3,"competitive":2,"self_skill":2,"fitness":3}}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/questionnaire/submit `
  -Headers @{ Authorization = "Bearer <TOKEN>" } -ContentType "application/json" -Body $body
```

Expected JSON: `provisional_rating: 1044`, `breakdown` matching the table above,
`is_first_attempt: true`. Resubmitting the same answers → `is_first_attempt:
false` and **no change** to the stored rating.

### 3. UI test

1. Log in → Dashboard → open `questionnaire.html`.
2. Try submitting with nothing selected → inline "Please choose an answer." errors.
3. Pick a sport, answer all 5 questions → Submit → green card shows the
   provisional rating and the full breakdown, with the provisional-estimate notice.
4. Refresh and resubmit → the notice explains the rating cannot be changed this way.
