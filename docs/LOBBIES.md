# Stage 6 — Match Lobby Management

## Concurrency-safe joining (the important part)

Joins and leaves run **inside PostgreSQL**, not Python:

```
join_lobby(p_lobby_id)   -- SECURITY DEFINER function (migration 005)
  1. auth.uid() must exist                      -> NOT_AUTHENTICATED
  2. SELECT ... FOR UPDATE locks the lobby row  -- concurrent joins
     serialize here; the second one re-reads fresh counts
  3. duplicate (lobby,user)?                    -> ALREADY_JOINED
  4. status <> 'open'?                          -> LOBBY_NOT_OPEN
  5. scheduled_at <= now()?                     -> LOBBY_ALREADY_STARTED
  6. count >= max_players?                      -> LOBBY_FULL
  7. INSERT participant; flip status to 'full' at capacity
```

Overbooking is impossible: the row lock serialises simultaneous requests, the
count re-check happens after the lock, and `unique (lobby_id, user_id)` (from
migration 001) blocks duplicates at the constraint level regardless.
`leave_lobby()` mirrors this and restores `open` when a place frees up.
A trigger (`sync_lobby_status`) keeps status correct even for direct writes.

Flask calls these RPCs **with the user's JWT** (so `auth.uid()` is the real
caller) via `rpc_join`/`rpc_leave` in `backend/services/lobby_service.py`.

## State machine

```
open ──► full ──► in_progress ──► completed
  │ \─────────────────┘───────▲
  └──────────► cancelled ◄────┘   (any active state can cancel; terminals frozen)
```

## API endpoints (all token-verified)

| Method & path | Who | Rules |
|---|---|---|
| `POST /api/lobbies` | any authed user | full validation (400 on bad input) |
| `GET /api/lobbies/mine` | host | lobbies they host |
| `GET /api/lobbies/<id>` | authed | participants + places available |
| `POST /api/lobbies/<id>/join` | authed | atomic RPC; 409 on dup/full/closed |
| `POST /api/lobbies/<id>/leave` | participant | atomic RPC; blocked after start |
| `POST /api/lobbies/<id>/start` | host only (403) | needs min_players (409) |
| `POST /api/lobbies/<id>/cancel` | host only (403) | any active state |

Required player count is **configurable per match** (`min_players`,
validated to be within [2×team_size, max_players]).

## Files

- `supabase/migrations/005_lobby_functions.sql` — RPCs + status-sync trigger
- `backend/services/lobby_service.py` — validation, state machine, RPC calls
- `backend/routes/lobby_management.py` — endpoints
- `frontend/create-lobby.html` + `js/pages/create-lobby.js` — create form
- `frontend/lobby.html` + `js/pages/lobby.js` — detail, join/leave, host controls
- `tests/test_lobby_service.py` — unit tests

## Running & testing

### 1. Apply migration 005 (SQL Editor), then unit tests

```powershell
python -m unittest tests.test_lobby_service -v   # Python-side rules, no DB
```

### 2. UI flow (two browser profiles for two users)

1. User A: log in → `create-lobby.html` → pick sport, ground, date/time,
   players per team 5, max 10 → Create → success toast → open lobby page.
2. Try invalid form (past date, team_size 5 with max_players 9) → inline errors.
3. User B: log in → find the lobby → Join → participants 2/10.
4. User B joins again (or reloads and clicks Join twice) → error
   *"You have already joined this lobby."* (409, DB-enforced).
5. Fill remaining places with test users → status flips to **Full**;
   further joins → *"This lobby is full."*
6. User B leaves → status back to **Open**, places_available +1.
7. User A (host) clicks **Start** before min_players → error showing how many
   more are needed; after enough join → status **In progress**; Join/Leave now
   blocked ("match already started").
8. User A cancels another lobby → **Cancelled**; joins rejected.
9. Non-host start/cancel → *"Only the host…"* (403).

### 3. Direct RPC concurrency test (SQL Editor, two tabs at once)

```sql
select public.join_lobby('<lobby-uuid>');  -- run in 2 tabs simultaneously
```

One succeeds, the other raises `ALREADY_JOINED`; with a full lobby the second
raises `LOBBY_FULL` — capacity can never be exceeded even under races.
