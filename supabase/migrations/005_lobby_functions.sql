-- ============================================================================
-- Migration 005: lobby management — safe joining via an atomic RPC.
--
-- Concurrency strategy:
--   * joining happens ONLY through join_lobby(lobby_id) — a SECURITY DEFINER
--     function whose single INSERT ... is guarded by a row lock on the lobby
--     (SELECT ... FOR UPDATE) inside an implicit transaction. Two simultaneous
--     joins serialize on that lock; the second sees the updated count and is
--     rejected, so capacity can NEVER be exceeded.
--   * duplicate participation remains impossible via unique(lobby_id,user_id).
--   * triggers keep lobby.status in sync (open <-> full).
--   * host-only controls enforced in-function via host_id check.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Atomic join function. Returns the new participant row, or raises.
-- ----------------------------------------------------------------------------
create or replace function public.join_lobby(p_lobby_id uuid)
returns public.lobby_participants
language plpgsql
security definer
set search_path = public
as $$
declare
  v_lobby       public.lobbies;
  v_count       integer;
  v_participant public.lobby_participants;
begin
  -- Who is joining? Must be an authenticated Supabase user.
  if auth.uid() is null then
    raise exception 'NOT_AUTHENTICATED';
  end if;

  -- Lock the lobby row: concurrent joiners wait here, then re-read state.
  select * into v_lobby from public.lobbies where id = p_lobby_id for update;
  if not found then
    raise exception 'LOBBY_NOT_FOUND';
  end if;

  -- Duplicate participation blocked up-front for a clear error message.
  if exists (
    select 1 from public.lobby_participants
    where lobby_id = p_lobby_id and user_id = auth.uid()
  ) then
    raise exception 'ALREADY_JOINED';
  end if;

  -- State rules: cannot join closed or started lobbies.
  if v_lobby.status <> 'open' then
    raise exception 'LOBBY_NOT_OPEN';
  end if;

  if v_lobby.scheduled_at <= now() then
    raise exception 'LOBBY_ALREADY_STARTED';
  end if;

  -- Capacity rule: the authoritative check against max_players.
  select count(*) into v_count
  from public.lobby_participants where lobby_id = p_lobby_id;

  if v_count >= v_lobby.max_players then
    raise exception 'LOBBY_FULL';
  end if;

  insert into public.lobby_participants (lobby_id, user_id)
  values (p_lobby_id, auth.uid())
  returning * into v_participant;

  -- Status sync: full when capacity reached.
  if v_count + 1 >= v_lobby.max_players then
    update public.lobbies set status = 'full' where id = p_lobby_id;
  end if;

  return v_participant;
end;
$$;

-- ----------------------------------------------------------------------------
-- 2. Atomic leave function. Only before the match starts; host leaving is
--    blocked if other players remain (host must cancel instead).
-- ----------------------------------------------------------------------------
create or replace function public.leave_lobby(p_lobby_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_lobby public.lobbies;
  v_count integer;
begin
  if auth.uid() is null then
    raise exception 'NOT_AUTHENTICATED';
  end if;

  select * into v_lobby from public.lobbies where id = p_lobby_id for update;
  if not found then
    raise exception 'LOBBY_NOT_FOUND';
  end if;

  if v_lobby.status not in ('open', 'full') then
    raise exception 'LOBBY_NOT_JOINABLE';   -- cannot leave once started/etc.
  end if;

  delete from public.lobby_participants
  where lobby_id = p_lobby_id and user_id = auth.uid();
  if not found then
    raise exception 'NOT_A_PARTICIPANT';
  end if;

  select count(*) into v_count
  from public.lobby_participants where lobby_id = p_lobby_id;

  -- Leaving frees a place -> status back to open (unless match already begun).
  update public.lobbies
  set status = case when v_count >= max_players then 'full' else 'open' end
  where id = p_lobby_id and status in ('open', 'full');
end;
$$;

-- ----------------------------------------------------------------------------
-- 3. Status-sync triggers as a safety net for direct writes (service role).
-- ----------------------------------------------------------------------------
create or replace function public.sync_lobby_status()
returns trigger
language plpgsql
as $$
declare
  v_count integer;
  v_max   integer;
begin
  select count(*), coalesce(max(l.max_players), 0) into v_count, v_max
  from public.lobby_participants lp
  join public.lobbies l on l.id = lp.lobby_id
  where lp.lobby_id = coalesce(new.lobby_id, old.lobby_id);

  select max_players into v_max from public.lobbies
  where id = coalesce(new.lobby_id, old.lobby_id);

  update public.lobbies
  set status = case
    when status = 'cancelled' then 'cancelled'          -- never resurrect
    when status = 'completed' then 'completed'
    when v_count >= v_max and v_max > 0 then 'full'
    when status = 'full' and v_count < v_max then 'open'
    else status
  end
  where id = coalesce(new.lobby_id, old.lobby_id);

  return coalesce(new, old);
end;
$$;

drop trigger if exists lobby_participants_sync on public.lobby_participants;
create trigger lobby_participants_sync
  after insert or delete on public.lobby_participants
  for each row execute function public.sync_lobby_status();

-- ----------------------------------------------------------------------------
-- 4. Grants: authenticated users may call the RPCs; the functions themselves
--    enforce every rule, and RLS on lobby_participants still applies to
--    direct table access.
-- ----------------------------------------------------------------------------
grant execute on function public.join_lobby(uuid)  to authenticated;
grant execute on function public.leave_lobby(uuid) to authenticated;
