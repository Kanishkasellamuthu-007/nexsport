-- ============================================================================
-- NexSport migration 003: seed data (safe to re-run: uses ON CONFLICT)
-- ============================================================================

-- Supported sports with configurable team sizes ------------------------------
insert into public.sports (code, name, team_size, min_players, max_players, description, icon)
values
  ('football', 'Football',   11, 4, 22, '11-a-side football on public grounds', '⚽'),
  ('basketball','Basketball',  5, 4, 10, '5-a-side basketball',                 '🏀'),
  ('cricket',  'Cricket',      11, 6, 22, 'Street / box cricket',                '🏏'),
  ('badminton','Badminton',     2, 2,  4, 'Doubles badminton',                   '🏸'),
  ('volleyball','Volleyball',   6, 4, 12, '6-a-side volleyball',                 '🏐')
on conflict (code) do nothing;

-- A few sample public grounds (edit coordinates to your city) ----------------
insert into public.grounds (name, address, city, latitude, longitude)
values
  ('Mumbai Marine Drive Promenade', 'Netaji Subhash Chandra Bose Road', 'Mumbai', 18.9440, 72.8235),
  ('Delhi India Gate Lawns',        'India Gate',                       'Delhi',  28.6129, 77.2295),
  ('Bengaluru Cubbon Park',         'Kasturba Road',                    'Bengaluru', 12.9763, 77.5929)
on conflict do nothing;

-- Questionnaire template (sport_id null = applies to every sport) ------------
insert into public.questionnaire_questions (sport_id, question_text, question_order, options)
values
  (null, 'How many years have you played this sport?', 1,
   '[{"label":"Never played","value":1},{"label":"1-2 years","value":2},{"label":"3-5 years","value":3},{"label":"5+ years","value":4}]'::jsonb),
  (null, 'How often do you play currently?', 2,
   '[{"label":"Rarely","value":1},{"label":"Monthly","value":2},{"label":"Weekly","value":3},{"label":"Almost daily","value":4}]'::jsonb),
  (null, 'Have you played at a competitive level?', 3,
   '[{"label":"No","value":1},{"label":"School/college level","value":2},{"label":"Club/district level","value":3},{"label":"State or above","value":4}]'::jsonb),
  (null, 'How confident are you in the core skills of this sport?', 4,
   '[{"label":"Beginner","value":1},{"label":"Intermediate","value":2},{"label":"Advanced","value":3}]'::jsonb),
  (null, 'How is your fitness/stamina?', 5,
   '[{"label":"Low","value":1},{"label":"Average","value":2},{"label":"High","value":3}]'::jsonb)
on conflict do nothing;
