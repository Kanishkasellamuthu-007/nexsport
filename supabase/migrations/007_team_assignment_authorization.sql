-- ==========================================================================
-- NexSport migration 007: authoritative and atomic team assignment
--
-- Ordinary users may not change team_side directly. Team assignment is
-- performed by the backend service role through assign_lobby_teams, which
-- validates the lobby host and all player assignments in one transaction.
-- Run this migration after 006_match_ratings.sql.
-- ==========================================================================

-- Replace the broad self-update policy. Only the lobby host may set teams.
drop policy if exists "lp_update_host" on public.lobby_participants;
create policy "lp_update_host" on public.lobby_participants
  for update
  using (
    exists (
      select 1
      from public.lobbies l
      where l.id = lobby_id
        and l.host_id = auth.uid()
    )
  )
  with check (
    exists (
      select 1
      from public.lobbies l
      where l.id = lobby_id
        and l.host_id = auth.uid()
    )
  );

create or replace function public.assign_lobby_teams(
  p_lobby_id uuid,
  p_host_id uuid,
  p_assignments jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_lobby public.lobbies;
  v_assignment jsonb;
  v_user_id uuid;
  v_team public.participant_side;
  v_assignment_count integer;
  v_distinct_count integer;
begin
  if p_assignments is null or jsonb_typeof(p_assignments) <> 'array' then
    raise exception 'INVALID_TEAM_ASSIGNMENTS';
  end if;

  select * into v_lobby
  from public.lobbies
  where id = p_lobby_id
  for update;

  if not found then
    raise exception 'LOBBY_NOT_FOUND';
  end if;
  if v_lobby.host_id <> p_host_id then
    raise exception 'ONLY_LOBBY_HOST';
  end if;
  if v_lobby.status not in ('open', 'full') then
    raise exception 'LOBBY_NOT_ASSIGNABLE';
  end if;

  select count(*), count(distinct (item->>'user_id'))
  into v_assignment_count, v_distinct_count
  from jsonb_array_elements(p_assignments) item;

  if v_assignment_count <> v_lobby.max_players
     or v_distinct_count <> v_assignment_count then
    raise exception 'INVALID_TEAM_ASSIGNMENTS';
  end if;

  -- Validate every row before applying it. The participant query must cover
  -- exactly the requested assignments, with no duplicate or foreign user id.
  for v_assignment in select * from jsonb_array_elements(p_assignments) loop
    begin
      v_user_id := (v_assignment->>'user_id')::uuid;
      v_team := (v_assignment->>'team_side')::public.participant_side;
    exception when others then
      raise exception 'INVALID_TEAM_ASSIGNMENTS';
    end;

    if v_team not in ('team_a', 'team_b') then
      raise exception 'INVALID_TEAM_ASSIGNMENTS';
    end;
    if not exists (
      select 1
      from public.lobby_participants lp
      where lp.lobby_id = p_lobby_id
        and lp.user_id = v_user_id
    ) then
      raise exception 'INVALID_TEAM_ASSIGNMENTS';
    end;
  end loop;

  if (
    select count(*)
    from public.lobby_participants lp
    where lp.lobby_id = p_lobby_id
      and not exists (
        select 1
        from jsonb_array_elements(p_assignments) item
        where (item->>'user_id')::uuid = lp.user_id
      )
  ) <> 0 then
    raise exception 'INVALID_TEAM_ASSIGNMENTS';
  end;

  -- Every update below is in the same transaction. A later failure rolls the
  -- whole operation back to the state observed before this function ran.
  for v_assignment in select * from jsonb_array_elements(p_assignments) loop
    v_user_id := (v_assignment->>'user_id')::uuid;
    v_team := (v_assignment->>'team_side')::public.participant_side;

    update public.lobby_participants
    set team_side = v_team
    where lobby_id = p_lobby_id
      and user_id = v_user_id;
  end loop;

  return jsonb_build_object(
    'ok', true,
    'lobby_id', p_lobby_id,
    'assigned', v_assignment_count
  );
end;
$$;

revoke execute on function public.assign_lobby_teams(uuid, uuid, jsonb) from public;
revoke execute on function public.assign_lobby_teams(uuid, uuid, jsonb) from anon;
revoke execute on function public.assign_lobby_teams(uuid, uuid, jsonb) from authenticated;
grant execute on function public.assign_lobby_teams(uuid, uuid, jsonb) to service_role;
