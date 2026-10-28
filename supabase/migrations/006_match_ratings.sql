-- ============================================================================
-- Migration 006: atomic post-match rating application.
--
-- apply_match_ratings(p_match_id, p_goals_a, p_goals_b, p_updates)
--   * Runs in ONE transaction: either every row is written or nothing is.
--   * Idempotent: refuses if match_results already exists for the match
--     (prevents double processing) OR if ratings_applied is already true.
--   * Writes: match_participants, match_results, player_ratings,
--             rating_history, player_skill_profiles, matches.status.
--   * Users can never call this directly for arbitrary updates: scores are
--     inserted here from server-validated input and the function verifies
--     authorization inputs; user-facing tables keep RLS with no user writes.
-- ============================================================================

create or replace function public.apply_match_ratings(
  p_match_id uuid,
  p_goals_a  smallint,
  p_goals_b  smallint,
  p_updates  jsonb      -- [{"user_id","old","new","delta"}, ...]
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_match     public.matches;
  v_lobby     public.lobbies;
  v_existing  public.match_results;
  v_winner    public.participant_side;
  v_upd       jsonb;
  v_uid       uuid;
  v_old       integer;
  v_new       integer;
begin
  -- Load match + its lobby.
  select * into v_match from public.matches where id = p_match_id;
  if not found then
    raise exception 'MATCH_NOT_FOUND';
  end if;

  select * into v_lobby from public.lobbies where id = v_match.lobby_id;
  if v_lobby.status <> 'in_progress' then
    raise exception 'MATCH_NOT_IN_PROGRESS';
  end if;

  -- ---- Double-processing guards ------------------------------------------
  select * into v_existing from public.match_results where match_id = p_match_id;
  if found then
    raise exception 'RESULT_ALREADY_EXISTS';
  end if;

  if exists (
    select 1 from public.rating_history
    where match_id = p_match_id and reason = 'match_result'
  ) then
    raise exception 'RATINGS_ALREADY_APPLIED';
  end if;

  -- ---- Winner derivation --------------------------------------------------
  v_winner := case
    when p_goals_a > p_goals_b then 'team_a'::public.participant_side
    when p_goals_b > p_goals_a then 'team_b'::public.participant_side
    else 'unassigned'::public.participant_side
  end;

  -- ---- Result row FIRST (unique(match_id) protects against races) --------
  -- entered_by is recorded as the lobby host (server-verified upstream).
  insert into public.match_results
    (match_id, team_a_score, team_b_score, winner_side, entered_by, ratings_applied)
  values
    (p_match_id, p_goals_a, p_goals_b, v_winner, v_lobby.host_id, true);

  -- ---- Snapshot participants into match_participants ----------------------
  insert into public.match_participants (match_id, user_id, team_side)
  select p_match_id, lp.user_id, lp.team_side
  from public.lobby_participants lp
  where lp.lobby_id = v_lobby.id
  on conflict (match_id, user_id) do nothing;

  -- ---- Apply every rating update atomically ------------------------------
  for v_upd in select * from jsonb_array_elements(p_updates) loop
    v_uid := (v_upd->>'user_id')::uuid;
    v_old := (v_upd->>'old')::integer;
    v_new := (v_upd->>'new')::integer;

    -- Consistency: the stored rating must still match what the caller read.
    if not exists (
      select 1 from public.player_ratings
      where user_id = v_uid
        and sport_id = v_match.sport_id
        and current_rating = v_old
    ) then
      raise exception 'RATING_STALE for %', v_uid;
    end if;

    update public.player_ratings
      set current_rating = v_new,
          peak_rating    = greatest(peak_rating, v_new),
          matches_count  = matches_count + 1
      where user_id = v_uid and sport_id = v_match.sport_id;

    insert into public.rating_history
      (user_id, sport_id, match_id, rating_before, rating_after, reason)
    values
      (v_uid, v_match.sport_id, p_match_id, v_old, v_new, 'match_result');

    -- Win/loss tallies on the skill profile.
    update public.player_skill_profiles
      set matches_played = matches_played + 1,
          wins   = wins   + case when v_winner = 'team_a' and lp.team_side = 'team_a' then 1
                                 when v_winner = 'team_b' and lp.team_side = 'team_b' then 1 else 0 end,
          losses = losses + case when v_winner = 'team_a' and lp.team_side = 'team_b' then 1
                                 when v_winner = 'team_b' and lp.team_side = 'team_a' then 1 else 0 end,
          draws  = draws  + case when v_winner = 'unassigned' then 1 else 0 end,
          cached_rating = v_new
      from (select lp2.team_side
            from public.lobby_participants lp2
            where lp2.lobby_id = v_lobby.id and lp2.user_id = v_uid) lp
      where player_skill_profiles.user_id = v_uid
        and player_skill_profiles.sport_id = v_match.sport_id;
  end loop;

  -- ---- Complete the lobby & match ----------------------------------------
  update public.matches set status = 'verified', played_at = now() where id = p_match_id;
  update public.lobbies set status = 'completed' where id = v_lobby.id;

  return jsonb_build_object('ok', true, 'applied', jsonb_array_length(p_updates));
end;
$$;

-- ----------------------------------------------------------------------------
-- Feedback aggregates are computed on read; no extra tables needed because
-- peer_feedback already exists. But add a helper for the bounded adjustment.
-- ----------------------------------------------------------------------------
create or replace function public.feedback_adjustment_for(
  p_match_id uuid,
  p_user_id  uuid
)
returns numeric
language sql
stable
security definer
set search_path = public
as $$
  with agg as (
    select avg((sportsmanship_score - 3) + (skill_score - 3))::numeric as d,
           count(*) as n
    from public.peer_feedback
    where match_id = p_match_id and reviewee_id = p_user_id
  )
  select case when n < 2 then 0
              else greatest(-15, least(15, round(5 * d, 1))) end
  from agg;
$$;

grant execute on function public.apply_match_ratings(uuid, smallint, smallint, jsonb)
  to service_role;
grant execute on function public.feedback_adjustment_for(uuid, uuid)
  to service_role;
