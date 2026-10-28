-- ============================================================================
-- NexSport migration 001: core schema
-- Tables, enums, constraints, indexes, updated_at triggers.
-- Run in the Supabase SQL Editor (or via supabase db push).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Extensions & helper: updated_at trigger
-- ----------------------------------------------------------------------------
create extension if not exists "pgcrypto";   -- gen_random_uuid()

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ----------------------------------------------------------------------------
-- Enums
-- ----------------------------------------------------------------------------
create type public.lobby_status     as enum ('open', 'full', 'in_progress', 'completed', 'cancelled');
create type public.lobby_visibility as enum ('public', 'invite_only');
create type public.match_status     as enum ('scheduled', 'entered', 'verified');
create type public.participant_side as enum ('team_a', 'team_b', 'unassigned');

-- ----------------------------------------------------------------------------
-- 1. USER PROFILES
-- One row per authenticated Supabase user (auth.users.id).
-- Sensitive columns live here; a public view (002) exposes only safe fields.
-- ----------------------------------------------------------------------------
create table public.profiles (
  id            uuid primary key references auth.users (id) on delete cascade,
  username      text not null unique check (char_length(username) between 3 and 30),
  full_name     text,
  avatar_url    text,
  bio           text check (char_length(bio) <= 500),
  phone         text,
  date_of_birth date,
  city          text,
  is_admin      boolean not null default false,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create trigger profiles_set_updated_at
  before update on public.profiles
  for each row execute function public.set_updated_at();

create index profiles_city_idx on public.profiles (city) where city is not null;

-- ----------------------------------------------------------------------------
-- 2. SUPPORTED SPORTS  (configurable team sizes -> schema supports any sport)
-- ----------------------------------------------------------------------------
create table public.sports (
  id               uuid primary key default gen_random_uuid(),
  code             text not null unique,              -- 'football', 'cricket', ...
  name             text not null,
  team_size        smallint not null check (team_size between 1 and 30),
  min_players      smallint not null check (min_players >= 2),
  max_players      smallint not null,
  check (max_players >= min_players),
  description      text,
  icon             text,                              -- emoji / icon name for UI
  is_active        boolean not null default true,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create trigger sports_set_updated_at
  before update on public.sports
  for each row execute function public.set_updated_at();

-- ----------------------------------------------------------------------------
-- 3. PLAYER SKILL PROFILES
-- Questionnaire-driven metadata per (user, sport). The authoritative current
-- Elo number lives in player_ratings; this table holds the player-facing
-- summary (questionnaire status, cached rating for display, career stats).
-- ----------------------------------------------------------------------------
create table public.player_skill_profiles (
  id                      uuid primary key default gen_random_uuid(),
  user_id                 uuid not null references public.profiles (id) on delete cascade,
  sport_id                uuid not null references public.sports (id) on delete cascade,
  questionnaire_completed boolean not null default false,
  cached_rating           integer not null default 1000,
  matches_played          integer not null default 0 check (matches_played >= 0),
  wins                    integer not null default 0 check (wins >= 0),
  losses                  integer not null default 0 check (losses >= 0),
  draws                   integer not null default 0 check (draws >= 0),
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now(),
  unique (user_id, sport_id),
  check (wins + losses + draws <= matches_played)
);

create trigger player_skill_profiles_set_updated_at
  before update on public.player_skill_profiles
  for each row execute function public.set_updated_at();

create index player_skill_profiles_sport_idx
  on public.player_skill_profiles (sport_id, cached_rating desc);

-- ----------------------------------------------------------------------------
-- 4. SELF-ASSESSMENT QUESTIONNAIRE
-- ----------------------------------------------------------------------------
create table public.questionnaire_questions (
  id             uuid primary key default gen_random_uuid(),
  sport_id       uuid references public.sports (id) on delete cascade, -- null = applies to all sports
  question_text  text not null,
  question_order smallint not null,
  is_active      boolean not null default true,
  -- jsonb answer options: [{"label": "...", "value": 1, "weight": 0.4}, ...]
  options        jsonb not null default '[]'::jsonb,
  created_at     timestamptz not null default now(),
  unique (sport_id, question_order)
);

create table public.questionnaire_responses (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references public.profiles (id) on delete cascade,
  question_id   uuid not null references public.questionnaire_questions (id) on delete cascade,
  sport_id      uuid not null references public.sports (id) on delete cascade,
  attempt_no    integer not null default 1 check (attempt_no >= 1),
  -- selected option label/value, validated by the service layer
  response      jsonb not null,
  created_at    timestamptz not null default now(),
  -- one answer per question per attempt (retaking the quiz = attempt_no+1)
  unique (user_id, question_id, attempt_no)
);

create index questionnaire_responses_user_sport_idx
  on public.questionnaire_responses (user_id, sport_id, attempt_no);

-- ----------------------------------------------------------------------------
-- 5. INITIAL PLAYER RATINGS
-- Server-side computed rating from the questionnaire (K-factor burn-in
-- period). Written ONLY by the service role, never by users.
-- ----------------------------------------------------------------------------
create table public.initial_ratings (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references public.profiles (id) on delete cascade,
  sport_id       uuid not null references public.sports (id) on delete cascade,
  attempt_no     integer not null default 1,
  rating         integer not null check (rating between 100 and 3000),
  computed_from  jsonb not null default '{}'::jsonb,  -- audit: questionnaire summary
  created_at     timestamptz not null default now(),
  unique (user_id, sport_id, attempt_no)
);

create index initial_ratings_user_sport_idx on public.initial_ratings (user_id, sport_id);

-- ----------------------------------------------------------------------------
-- 6. PUBLIC SPORTS GROUNDS  (latitude/longitude for Haversine)
-- ----------------------------------------------------------------------------
create table public.grounds (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  address     text,
  city        text,
  latitude    double precision not null check (latitude  between  -90 and  90),
  longitude   double precision not null check (longitude between -180 and 180),
  sports      uuid[] not null default '{}'::uuid[],  -- sport ids playable here
  is_active   boolean not null default true,
  created_by  uuid references public.profiles (id) on delete set null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (name, latitude, longitude)
);

create trigger grounds_set_updated_at
  before update on public.grounds
  for each row execute function public.set_updated_at();

create index grounds_location_idx on public.grounds (latitude, longitude);
create index grounds_city_idx on public.grounds (city) where city is not null;

-- ----------------------------------------------------------------------------
-- 7. MATCH LOBBIES  (host can pick a known ground OR drop custom coordinates)
-- ----------------------------------------------------------------------------
create table public.lobbies (
  id           uuid primary key default gen_random_uuid(),
  host_id      uuid not null references public.profiles (id) on delete cascade,
  sport_id     uuid not null references public.sports (id) on delete restrict,
  ground_id    uuid references public.grounds (id) on delete set null,
  title        text not null check (char_length(title) between 3 and 100),
  description  text check (char_length(description) <= 1000),
  latitude     double precision not null check (latitude  between  -90 and  90),
  longitude    double precision not null check (longitude between -180 and 180),
  scheduled_at timestamptz not null,
  team_size    smallint not null check (team_size between 1 and 30),
  min_players  smallint not null check (min_players >= 2),
  max_players  smallint not null,
  check (max_players >= min_players),
  status       public.lobby_status not null default 'open',
  visibility   public.lobby_visibility not null default 'public',
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create trigger lobbies_set_updated_at
  before update on public.lobbies
  for each row execute function public.set_updated_at();

create index lobbies_sport_status_idx   on public.lobbies (sport_id, status);
create index lobbies_location_idx       on public.lobbies (latitude, longitude);
create index lobbies_scheduled_at_idx   on public.lobbies (scheduled_at);
create index lobbies_host_idx           on public.lobbies (host_id);

-- ----------------------------------------------------------------------------
-- 8. LOBBY PARTICIPANTS  (duplicate participation blocked by unique key;
--    team assignment zig-zag output stored in team_side)
-- ----------------------------------------------------------------------------
create table public.lobby_participants (
  id         uuid primary key default gen_random_uuid(),
  lobby_id   uuid not null references public.lobbies (id) on delete cascade,
  user_id    uuid not null references public.profiles (id) on delete cascade,
  team_side  public.participant_side not null default 'unassigned',
  joined_at  timestamptz not null default now(),
  unique (lobby_id, user_id)                     -- <- no duplicate joins
);

create index lobby_participants_user_idx on public.lobby_participants (user_id);
create index lobby_participants_lobby_idx on public.lobby_participants (lobby_id, team_side);

-- ----------------------------------------------------------------------------
-- 9. MATCHES  (one scheduled/played fixture per lobby)
-- ----------------------------------------------------------------------------
create table public.matches (
  id          uuid primary key default gen_random_uuid(),
  lobby_id    uuid not null references public.lobbies (id) on delete cascade,
  sport_id    uuid not null references public.sports (id) on delete restrict,
  played_at   timestamptz,
  status      public.match_status not null default 'scheduled',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (lobby_id)                              -- one match per lobby
);

create trigger matches_set_updated_at
  before update on public.matches
  for each row execute function public.set_updated_at();

create index matches_sport_status_idx on public.matches (sport_id, status);

-- Match participants: which players actually showed up, and on which side.
create table public.match_participants (
  id         uuid primary key default gen_random_uuid(),
  match_id   uuid not null references public.matches (id) on delete cascade,
  user_id    uuid not null references public.profiles (id) on delete cascade,
  team_side  public.participant_side not null default 'unassigned',
  created_at timestamptz not null default now(),
  unique (match_id, user_id)
);

create index match_participants_user_idx on public.match_participants (user_id);

-- ----------------------------------------------------------------------------
-- 10a. MATCH RESULTS  (authoritative scores; duplicate processing prevented
--      by unique(match_id) + idempotency_key unique where provided)
-- ----------------------------------------------------------------------------
create table public.match_results (
  id              uuid primary key default gen_random_uuid(),
  match_id        uuid not null unique references public.matches (id) on delete cascade,
  team_a_score    smallint not null check (team_a_score >= 0),
  team_b_score    smallint not null check (team_b_score >= 0),
  winner_side     public.participant_side not null check (winner_side in ('team_a','team_b','unassigned')),
  entered_by      uuid not null references public.profiles (id) on delete restrict,
  ratings_applied boolean not null default false,   -- Elo applied by service role
  idempotency_key text unique,                       -- client retry-safety token
  created_at      timestamptz not null default now()
);

create index match_results_entered_by_idx on public.match_results (entered_by);

-- ----------------------------------------------------------------------------
-- 10b. PLAYER RATINGS (current, AUTHORITATIVE) + 10c. RATING HISTORY
-- player_ratings: service-role writes ONLY (no RLS policies for users).
-- rating_history: append-only ledger of every Elo change.
-- ----------------------------------------------------------------------------
create table public.player_ratings (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references public.profiles (id) on delete cascade,
  sport_id      uuid not null references public.sports (id) on delete cascade,
  current_rating integer not null default 1000 check (current_rating between 100 and 3000),
  peak_rating   integer not null default 1000,
  matches_count integer not null default 0 check (matches_count >= 0),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (user_id, sport_id)
);

create trigger player_ratings_set_updated_at
  before update on public.player_ratings
  for each row execute function public.set_updated_at();

create index player_ratings_sport_idx on public.player_ratings (sport_id, current_rating desc);

create table public.rating_history (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references public.profiles (id) on delete cascade,
  sport_id      uuid not null references public.sports (id) on delete cascade,
  match_id      uuid references public.matches (id) on delete set null,
  rating_before integer not null,
  rating_after  integer not null,
  rating_delta  integer generated always as (rating_after - rating_before) stored,
  reason        text not null default 'match_result',  -- 'match_result' | 'initial_rating'
  created_at    timestamptz not null default now(),
  unique (user_id, sport_id, match_id, reason)
);

create index rating_history_user_sport_idx on public.rating_history (user_id, sport_id, created_at desc);

-- ----------------------------------------------------------------------------
-- 11. PEER FEEDBACK  (post-match reviews between teammates/opponents)
-- ----------------------------------------------------------------------------
create table public.peer_feedback (
  id                  uuid primary key default gen_random_uuid(),
  match_id            uuid not null references public.matches (id) on delete cascade,
  reviewer_id         uuid not null references public.profiles (id) on delete cascade,
  reviewee_id         uuid not null references public.profiles (id) on delete cascade,
  sportsmanship_score smallint not null check (sportsmanship_score between 1 and 5),
  skill_score         smallint not null check (skill_score between 1 and 5),
  comment             text check (char_length(comment) <= 500),
  created_at          timestamptz not null default now(),
  unique (match_id, reviewer_id, reviewee_id),      -- one review per pair per match
  check (reviewer_id <> reviewee_id)                -- cannot review yourself
);

create index peer_feedback_reviewee_idx on public.peer_feedback (reviewee_id);

-- ----------------------------------------------------------------------------
-- 12. MATCH STATISTICS  (per-player stats; jsonb allows sport-specific keys)
-- ----------------------------------------------------------------------------
create table public.match_statistics (
  id           uuid primary key default gen_random_uuid(),
  match_id     uuid not null references public.matches (id) on delete cascade,
  user_id      uuid not null references public.profiles (id) on delete cascade,
  team_side    public.participant_side not null default 'unassigned',
  goals        smallint not null default 0 check (goals >= 0),
  assists      smallint not null default 0 check (assists >= 0),
  custom_stats jsonb not null default '{}'::jsonb,   -- e.g. {"wickets": 2} for cricket
  created_at   timestamptz not null default now(),
  unique (match_id, user_id)
);

create index match_statistics_user_idx on public.match_statistics (user_id);
