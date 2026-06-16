-- PVMath: enable multiple saved projects per user
-- Currently user_projects has NO id column and user_id itself is the PRIMARY KEY,
-- which limits every user to exactly one row, ever. This migration adds a proper
-- per-project id, makes IT the primary key instead, and keeps user_id indexed.
-- Safe to run as-is — it does not delete any existing data.

-- 1. Add the new id column (nullable for now, so existing rows aren't rejected)
alter table public.user_projects add column if not exists id uuid;

-- 2. Backfill existing rows with unique ids
update public.user_projects set id = gen_random_uuid() where id is null;

-- 3. Make id required, and auto-generate it for all future inserts
alter table public.user_projects alter column id set not null;
alter table public.user_projects alter column id set default gen_random_uuid();

-- 4. Drop the current primary key (it's on user_id — run the SELECT below first
--    if this exact constraint name errors, to find the real one):
--    select conname from pg_constraint
--    where conrelid = 'public.user_projects'::regclass and contype = 'p';
alter table public.user_projects drop constraint user_projects_pkey;

-- 5. Make id the new primary key
alter table public.user_projects add primary key (id);

-- 6. Keep per-user lookups fast now that user_id is no longer unique
create index if not exists user_projects_user_id_idx on public.user_projects (user_id);
