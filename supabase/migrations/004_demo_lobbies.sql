-- ============================================================================
-- Migration 004: demonstration lobbies for location-based discovery testing.
-- DEMO DATA ONLY — clearly labelled; delete once real usage begins.
--
-- Haversine does NOT discover grounds: these rows exist so the nearby-search
-- endpoint has something to rank. Verified ground data can later be imported
-- from OpenStreetMap (Overpass API) or another open geo source into `grounds`.
-- Safe to re-run (guards on unique title).
-- ============================================================================

-- Resolve sport ids by code --------------------------------------------------
-- football / basketball from 003_seed_data.sql

insert into public.lobbies
  (host_id, sport_id, ground_id, title, description, latitude, longitude,
   scheduled_at, team_size, min_players, max_players, status, visibility)
select
  p.id, s.id, null,
  t.title, t.description, t.lat, t.lon,
  now() + (t.hours_ahead || ' hours')::interval,
  t.team_size, t.min_players, t.max_players, 'open', 'public'
from (values
  ('Evening Football near Marine Drive', '7-a-side casual football, all levels welcome.', 18.9440, 72.8235, 20, 7, 6, 14),
  ('Morning Basketball at India Gate',   '3v3 half-court, friendly pace.',           28.6129, 77.2295, 30, 5, 4, 10),
  ('Weekend Cricket near Cubbon Park',   'Box cricket, 8 overs a side.',             12.9763, 77.5929, 50, 11, 6, 22),
  ('Sunset Volleyball at Marina',        '6-a-side beach-style volleyball.',         13.0550, 80.2820, 26, 6, 4, 12)
) as t(title, description, lat, lon, hours_ahead, team_size, min_players, max_players)
join public.sports s on s.code = case
    when t.title like 'Evening Football%' then 'football'
    when t.title like 'Morning Basketball%' then 'basketball'
    when t.title like 'Weekend Cricket%' then 'cricket'
    else 'volleyball' end
join public.profiles p on true                       -- any profile hosts demos
where not exists (select 1 from public.lobbies l where l.title = t.title);

-- One FULL lobby to verify that full lobbies are not offered as joinable ----
insert into public.lobbies
  (host_id, sport_id, ground_id, title, description, latitude, longitude,
   scheduled_at, team_size, min_players, max_players, status, visibility)
select p.id, s.id, null,
  'FULL — Badminton Doubles Test', 'Demo lobby marked full; must show as not joinable.',
  19.0760, 72.8777,
  now() + interval '15 hours', 2, 2, 2, 'full', 'public'
from public.profiles p
join public.sports s on s.code = 'badminton'
where not exists (select 1 from public.lobbies l where l.title = 'FULL — Badminton Doubles Test');
