# NexSport — Stage 8: Improved Greedy Zig-Zag Split Algorithm

## Simple explanation (for the presentation)

Imagine a captain picking players for two school teams. A naive captain picks
the best player first, then the next best, alternating — that's the **zig-zag
(snake) draft**: sort everyone by skill, give #1 to Team A, #2 to Team B,
#3 to Team A, and so on. It usually produces decent teams.

But sometimes the draft leaves Team A slightly stronger. Our **improvement
step** then plays "matchmaker": it tries every possible one-for-one trade
between the teams and performs the trade that makes the teams' total skill
closest — repeating until no trade helps. It's like tidying up the lineups
one swap at a time.

Honest caveat: balanced partitioning is NP-hard, so this greedy method is
**not guaranteed to find the globally optimal split** — but it consistently
produces near-optimal, fair teams, is fully deterministic, and provably
terminates (the difference strictly decreases each pass, bounded by 50 passes).

## Algorithm

```
1. Sort players by rating DESC, tie-break user_id ASC  (deterministic)
2. Snake draft: alternate players to Team A / Team B     (baseline phase)
3. signed = sum(A) − sum(B)
4. Repeat ≤ 50 passes:
     find the A↔B swap minimising |signed − 2·(a − b)| − |signed|
     if a strictly-improving swap exists → apply it; else stop
5. Return: assignments, totals, averages, |difference|
```

Ratings are **read-only** inside the algorithm (req. 12); validation rejects
empty input, odd counts, wrong expected counts, duplicate IDs, missing
fields, and bad ratings (req. 11). Output ordering is deterministic.

## Baseline vs improved — example output

`players(1900, 1800, 1000, 900)`:

| Split | Team A | Team B | Difference |
|---|---|---|---|
| Baseline zig-zag | 1900+1000 = 2900 | 1800+900 = 2700 | **200** |
| Improved | 1900+900 = 2800 | 1800+1000 = 2800 | **0** ✓ |

*(verified by the executed test suite — 83/83 tests pass)*

Identical ratings (10×1000): difference **0**, no improvement pass needed.
The full 22-player randomised sweep in the tests asserts
`improved ≤ baseline` for every case (never worse, often better).

## Usage from the app

- `POST /api/lobbies/<id>/teams` — **host only**, requires the lobby to be
  **full** (`joined == max_players`) and status `open`/`full` (req. 14).
  Reads authoritative `player_ratings`, runs the algorithm, stores
  `team_side` on `lobby_participants`.
- `GET /api/lobbies/<id>/teams` — view stored assignments.
- Post-generation edits are host-only actions; ordinary users have no write
  path to `team_side` beyond joining/leaving (stage 6 rules).
- New file: `backend/routes/teams.py`; host button "⚡ Generate balanced
  teams" on the lobby page.

## Testing

```powershell
python -m unittest tests.test_team_split -v     # pure Python, no DB
```

All required cases covered: 10 players, 22 players, identical ratings,
extreme differences, invalid counts, duplicate IDs, empty input,
no-improvement-possible, plus the baseline-comparison report and a
determinism test (same input → identical output).
