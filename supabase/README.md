# NexSport Database Design (Supabase PostgreSQL)

All SQL lives in `supabase/migrations/` and is meant to run **in order** in the
Supabase SQL Editor:

1. `001_initial_schema.sql` — tables, enums, constraints, indexes, triggers
2. `002_rls_policies.sql` — Row Level Security policies + public profile view
3. `003_seed_data.sql` — sample sports, grounds, questionnaire template
4. `004_demo_lobbies.sql` — demo lobby rows for local discovery
5. `005_lobby_functions.sql` — atomic join/leave RPCs and status trigger
6. `006_match_ratings.sql` — atomic post-match Elo application RPC
7. `007_team_assignment_authorization.sql` — host-only team assignment RPC and RLS policy

## How to run

1. Open your project at [supabase.com](https://supabase.com) → **SQL Editor** → *New query*.
2. Paste the **entire contents** of `001_initial_schema.sql` → **Run**.
3. Repeat migrations `002` through `007` in numeric order. Do not skip `007`
   when upgrading an existing project: it replaces the broad participant update policy.
4. No credentials are needed in the SQL editor — you are already authenticated
   as the project owner (service role). The browser/website never sees these;
   it only ever uses the **anon (publishable) key**.

## Tables & purpose

| Table | Purpose | Key rules |
|---|---|---|
| `profiles` | One row per authenticated Supabase user (`auth.users.id`). Holds contact details. | PK = auth user id (cascade on account delete); unique username |
| `sports` | Catalogue of supported sports with **configurable team sizes**. | unique `code`, team_size/min/max checks |
| `player_skill_profiles` | Per (user, sport) summary: questionnaire status, cached rating, career W/L/D. | unique (user_id, sport_id) |
| `questionnaire_questions` | Question bank; `sport_id NULL` = applies to all sports; options in jsonb. | unique (sport_id, question_order) |
| `questionnaire_responses` | User answers per attempt (retake = new attempt_no). | unique (user, question, attempt) |
| `initial_ratings` | Server-computed starting Elo from the questionnaire. | users can only SELECT their own; writes via service role |
| `grounds` | Public sports grounds with lat/lng (Haversine-ready). | unique (name, lat, lng); range checks |
| `lobbies` | Match lobbies; host may pin a ground or custom lat/lng; configurable team_size/min/max. | status & visibility enums; only host modifies |
| `lobby_participants` | Who joined a lobby; `team_side` stores zig-zag assignment. | **unique (lobby_id, user_id)** → no duplicate joins |
| `matches` | One fixture per lobby. | **unique (lobby_id)** |
| `match_participants` | Players who actually played and their side. | unique (match_id, user_id) |
| `match_results` | Authoritative final score per match. | **unique (match_id)** + `idempotency_key` unique → no duplicate processing; `ratings_applied` flag |
| `player_ratings` | Current authoritative Elo per (user, sport) + peak. | unique (user_id, sport_id); **no user write policies** |
| `rating_history` | Append-only Elo ledger (before/after/delta/reason). | unique (user, sport, match, reason) |
| `peer_feedback` | Post-match 1–5 ratings between players. | unique (match, reviewer, reviewee); can't review self |
| `match_statistics` | Per-player stats; `custom_stats` jsonb for sport-specific metrics. | unique (match_id, user_id) |

All tables have `created_at`; mutable tables also have `updated_at` maintained
by the `set_updated_at()` trigger.

## Security model (RLS)

- **Own profile**: users read/update only their own `profiles` row. Everyone can
  read `profiles_public` (a view that excludes `phone` and `date_of_birth`).
- **Public data**: sports, grounds, public lobbies, public lobby rosters are
  readable by anyone (including anonymous).
- **Invite-only lobbies**: readable only by the host and joined members.
- **Self-service participation**: users can insert/delete their own
  `lobby_participants` row. Only the host may call the backend atomic team
  assignment RPC; ordinary authenticated users cannot change `team_side` directly.
- **Authoritative ratings locked**: `player_ratings`, `rating_history`,
  `initial_ratings`, `matches`, `match_results` have **no INSERT/UPDATE/DELETE
  policies for users** — only the backend using the **service-role key** (never
  exposed to the browser) writes them. Users can SELECT their own rating rows.
- `anon` role has DELETE revoked on all tables as defense-in-depth.

## Test queries (run in SQL Editor)

```sql
-- 1. Tables created
select tablename from pg_tables where schemaname = 'public' order by tablename;

-- 2. RLS enabled everywhere
select relname, relrowsecurity from pg_class
where relnamespace = 'public'::regnamespace and relkind = 'r'
order by relname;

-- 3. Policies installed
select tablename, policyname, cmd from pg_policies
where schemaname = 'public' order by tablename, policyname;

-- 4. Seed data
select code, name, team_size, min_players, max_players from public.sports;
select name, city, latitude, longitude from public.grounds;

-- 5. Unique constraints exist (duplicate prevention)
select conrelid::regclass as tbl, conname, pg_get_constraintdef(oid)
from pg_constraint
where contype = 'u' and conrelid::regnamespace = 'public'::regnamespace;

-- 6. Enums
select typname, enumlabel from pg_enum
join pg_type on pg_type.oid = enumtypid order by typname, enumsortorder;

-- 7. Public view hides sensitive fields (should show no phone/dob columns)
select column_name from information_schema.columns
where table_name = 'profiles_public';
```

## Verifying RLS as a real user (later, once auth is wired)

After Stage 3 (auth screens), verify from the app: a logged-in user should see
only their own `profiles` row via `select * from profiles`, while
`select * from profiles_public` returns everyone — confirming policies work.

## Next stage

Frontend authentication screens (email/password + Google OAuth) will use the
**anon key only**; the service-role key stays server-side in Flask env vars.
