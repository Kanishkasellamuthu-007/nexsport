-- Private evidence and review status for skill verification requests.
create table public.skill_verification_submissions (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references public.profiles (id) on delete cascade,
  method          text not null check (method in ('results', 'images', 'certificate', 'coach')),
  note            text check (char_length(note) <= 1000),
  evidence_paths  text[] not null,
  evidence_count  smallint not null check (evidence_count between 1 and 3),
  status          text not null default 'pending'
                  check (status in ('pending', 'approved', 'rejected')),
  decision_note   text,
  reviewed_at     timestamptz,
  created_at      timestamptz not null default now(),
  check (cardinality(evidence_paths) = evidence_count)
);

create index skill_verification_submissions_user_created_idx
  on public.skill_verification_submissions (user_id, created_at desc);

alter table public.skill_verification_submissions enable row level security;

create policy "verification_submissions_select_own"
  on public.skill_verification_submissions
  for select using (auth.uid() = user_id);

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'skill-evidence',
  'skill-evidence',
  false,
  5242880,
  array['image/jpeg', 'image/png', 'image/webp', 'application/pdf']
)
on conflict (id) do update set
  public = false,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

create policy "skill_evidence_read_own"
  on storage.objects
  for select to authenticated
  using (
    bucket_id = 'skill-evidence'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

create policy "skill_evidence_insert_own"
  on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'skill-evidence'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

create policy "skill_evidence_delete_own"
  on storage.objects
  for delete to authenticated
  using (
    bucket_id = 'skill-evidence'
    and (storage.foldername(name))[1] = auth.uid()::text
  );
