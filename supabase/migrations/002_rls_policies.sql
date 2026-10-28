-- ============================================================================
-- NexSport migration 002: Row Level Security policies
--
-- Model:
--  * Users always read/write THEIR OWN profile rows.
--  * A public view exposes only non-sensitive profile fields to everyone.
--  * Sports, grounds, lobbies and lobby membership are publicly readable.
--  * Only hosts can update/cancel their lobbies; participants join/leave
--    themselves.
--  * Authoritative data — player_ratings, rating_history, initial_ratings,
--    matches, match_results — is NOT writable by ordinary users. Only the
--    service_role (backend) writes those; users get SELECT-only access to
--    their own rating data.
-- ============================================================================

-- Enable RLS on every table ---------------------------------------------------
alter table public.profiles                 enable row level security;
alter table public.sports                   enable row level security;
alter table public.player_skill_profiles    enable row level security;
alter table public.questionnaire_questions  enable row level security;
alter table public.questionnaire_responses  enable row level security;
alter table public.initial_ratings          enable row level security;
alter table public.grounds                  enable row level security;
alter table public.lobbies                  enable row level security;
alter table public.lobby_participants       enable row level security;
alter table public.matches                  enable row level security;
alter table public.match_participants       enable row level security;
alter table public.match_results            enable row level security;
alter table public.player_ratings           enable row level security;
alter table public.rating_history           enable row level security;
alter table public.peer_feedback            enable row level security;
alter table public.match_statistics         enable row level security;

-- Helper: is the caller authenticated? ---------------------------------------
create or replace function public.is_authenticated()
returns boolean language sql stable as $$
  select auth.role() = 'authenticated';
$$;

-- ============================================================================
-- PROFILES
-- ============================================================================
create policy "profiles_select_own" on public.profiles
  for select using (auth.uid() = id);

create policy "profiles_insert_own" on public.profiles
  for insert with check (auth.uid() = id);

create policy "profiles_update_own" on public.profiles
  for update using (auth.uid() = id) with check (auth.uid() = id);

-- no delete policy: accounts are removed via auth cascade only

-- Public, NON-SENSITIVE view of profiles (anonymous-readable).
-- Excludes: phone, date_of_birth, email-ish data. Keeps username, avatar, city, ratings summary via join in app layer.
create or replace view public.profiles_public
with (security_invoker = false) as            -- view runs as owner -> readable by anon
  select id, username, full_name, avatar_url, bio, city, is_admin, created_at
  from public.profiles;

grant select on public.profiles_public to anon, authenticated;

-- ============================================================================
-- SPORTS  (read-only for everyone; managed via service role / dashboard)
-- ============================================================================
create policy "sports_select_all" on public.sports
  for select using (true);

-- ============================================================================
-- PLAYER SKILL PROFILES: users read their own; everyone reads the summary
-- needed for team balancing is done server-side, so keep it own-only.
-- ============================================================================
create policy "psp_select_own" on public.player_skill_profiles
  for select using (auth.uid() = user_id);
create policy "psp_insert_own" on public.player_skill_profiles
  for insert with check (auth.uid() = user_id);
create policy "psp_update_own" on public.player_skill_profiles
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ============================================================================
-- QUESTIONNAIRE
-- ============================================================================
create policy "qq_select_all" on public.questionnaire_questions
  for select using (true);

create policy "qr_select_own" on public.questionnaire_responses
  for select using (auth.uid() = user_id);
create policy "qr_insert_own" on public.questionnaire_responses
  for insert with check (auth.uid() = user_id);
-- users may correct an answer within the same attempt
create policy "qr_update_own" on public.questionnaire_responses
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ============================================================================
-- INITIAL RATINGS: read-only for the owner; computed/written by service role
-- ============================================================================
create policy "ir_select_own" on public.initial_ratings
  for select using (auth.uid() = user_id);

-- ============================================================================
-- GROUNDS: public read, any authenticated user can add a ground,
-- only the creator can edit it.
-- ============================================================================
create policy "grounds_select_all" on public.grounds
  for select using (true);
create policy "grounds_insert_auth" on public.grounds
  for insert with check (auth.uid() = created_by);
create policy "grounds_update_owner" on public.grounds
  for update using (auth.uid() = created_by) with check (auth.uid() = created_by);

-- ============================================================================
-- LOBBIES: everyone reads PUBLIC lobbies; hosts read their own invite-only
-- lobbies; only the host modifies.
-- ============================================================================
create policy "lobbies_select" on public.lobbies
  for select using (
    visibility = 'public' or auth.uid() = host_id
  );
create policy "lobbies_insert_own" on public.lobbies
  for insert with check (auth.uid() = host_id);
create policy "lobbies_update_host" on public.lobbies
  for update using (auth.uid() = host_id) with check (auth.uid() = host_id);
create policy "lobbies_delete_host" on public.lobbies
  for delete using (auth.uid() = host_id);

-- ============================================================================
-- LOBBY PARTICIPANTS: lobby members visible to everyone for public lobbies;
-- users manage their own participation (join/leave).
-- ============================================================================
create policy "lp_select" on public.lobby_participants
  for select using (
    exists (
      select 1 from public.lobbies l
      where l.id = lobby_id
        and (l.visibility = 'public' or l.host_id = auth.uid())
    )
    or user_id = auth.uid()
  );
create policy "lp_insert_self" on public.lobby_participants
  for insert with check (auth.uid() = user_id);
create policy "lp_delete_self" on public.lobby_participants
  for delete using (auth.uid() = user_id);
-- host may also assign teams (update team_side)
create policy "lp_update_host" on public.lobby_participants
  for update using (
    exists (select 1 from public.lobbies l where l.id = lobby_id and l.host_id = auth.uid())
    or user_id = auth.uid()
  );

-- ============================================================================
-- MATCHES / MATCH PARTICIPANTS: readable by lobby members; writes by service
-- role only (no insert/update/delete policies for users).
-- ============================================================================
create policy "matches_select_lobby_members" on public.matches
  for select using (
    exists (
      select 1
      from public.lobby_participants lp
      join public.lobbies l on l.id = lp.lobby_id
      where lp.lobby_id = matches.lobby_id
        and (lp.user_id = auth.uid() or l.host_id = auth.uid() or l.visibility = 'public')
    )
  );

create policy "mp_select_lobby_members" on public.match_participants
  for select using (
    exists (
      select 1
      from public.matches m
      join public.lobbies l on l.id = m.lobby_id
      left join public.lobby_participants lp
        on lp.lobby_id = l.id and lp.user_id = auth.uid()
      where m.id = match_participants.match_id
        and (lp.user_id is not null or l.host_id = auth.uid() or l.visibility = 'public')
    )
  );

-- ============================================================================
-- MATCH RESULTS: participants of the lobby can read; NO user write policies.
-- Result entry + Elo application happen through the backend service role.
-- ============================================================================
create policy "mr_select_participants" on public.match_results
  for select using (
    exists (
      select 1
      from public.matches m
      join public.lobbies l on l.id = m.lobby_id
      left join public.lobby_participants lp on lp.lobby_id = l.id and lp.user_id = auth.uid()
      where m.id = match_results.match_id
        and (lp.user_id is not null or l.host_id = auth.uid() or l.visibility = 'public')
    )
  );

-- ============================================================================
-- PLAYER RATINGS & HISTORY: own rows readable; NO user insert/update/delete.
-- Only service_role (bypasses RLS as table owner) writes these.
-- ============================================================================
create policy "pr_select_own" on public.player_ratings
  for select using (auth.uid() = user_id);

create policy "rh_select_own" on public.rating_history
  for select using (auth.uid() = user_id);

-- ============================================================================
-- PEER FEEDBACK: reviews visible to lobby participants; you can only write
-- reviews about a match you took part in, and only about others.
-- ============================================================================
create policy "pf_select_participants" on public.peer_feedback
  for select using (
    reviewer_id = auth.uid()
    or reviewee_id = auth.uid()
    or exists (
      select 1
      from public.matches m
      join public.lobbies l on l.id = m.lobby_id
      left join public.lobby_participants lp on lp.lobby_id = l.id and lp.user_id = auth.uid()
      where m.id = peer_feedback.match_id
        and (lp.user_id is not null or l.host_id = auth.uid() or l.visibility = 'public')
    )
  );

create policy "pf_insert_participant" on public.peer_feedback
  for insert with check (
    reviewer_id = auth.uid()
    and reviewer_id <> reviewee_id
    and exists (
      select 1 from public.match_participants mp
      where mp.match_id = peer_feedback.match_id and mp.user_id = auth.uid()
    )
  );

-- ============================================================================
-- MATCH STATISTICS: readable within lobby; writable only about yourself.
-- ============================================================================
create policy "ms_select_participants" on public.match_statistics
  for select using (
    user_id = auth.uid()
    or exists (
      select 1
      from public.matches m
      join public.lobbies l on l.id = m.lobby_id
      left join public.lobby_participants lp on lp.lobby_id = l.id and lp.user_id = auth.uid()
      where m.id = match_statistics.match_id
        and (lp.user_id is not null or l.host_id = auth.uid() or l.visibility = 'public')
    )
  );

create policy "ms_insert_self" on public.match_statistics
  for insert with check (auth.uid() = user_id);

-- ============================================================================
-- Ensure anon/authenticated roles only get intended table grants.
-- (Supabase defaults grant all on public to anon+authenticated; RLS policies
-- above are what actually protect the rows. Explicitly revoke dangerous
-- defaults for extra safety.)
-- ============================================================================
revoke delete on all tables in schema public from anon;
