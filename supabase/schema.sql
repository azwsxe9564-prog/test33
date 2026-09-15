-- Run this in Supabase Dashboard → SQL Editor → New query.
-- Stores each signed-in user's study progress and stats in their own row.
create table if not exists public.study_progress (
  user_id uuid primary key references auth.users(id) on delete cascade,
  state jsonb not null default '{"version":2,"pools":{},"active":null,"updatedAt":null}'::jsonb,
  stats jsonb not null default '{"attempts":0,"correct":0}'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.study_progress enable row level security;

-- Users can read only their own progress.
create policy "Users can read own study progress"
on public.study_progress for select
to authenticated
using (auth.uid() = user_id);

-- Users can create only their own progress row.
create policy "Users can insert own study progress"
on public.study_progress for insert
to authenticated
with check (auth.uid() = user_id);

-- Users can update only their own progress row.
create policy "Users can update own study progress"
on public.study_progress for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);
