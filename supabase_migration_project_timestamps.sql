-- PVMath: add created_at / updated_at to user_projects
-- Root cause of "Could not list projects": api/routers/projects.py list_projects()
-- orders by `updated_at.desc.nullslast,created_at.desc`, but these columns were
-- never created (supabase_migration_multi_project.sql only added `id`). PostgREST
-- rejects the order= clause with a 400, surfacing as the generic error in the UI.
-- Safe to run as-is — additive only, no data loss.

alter table public.user_projects add column if not exists created_at timestamptz not null default now();
alter table public.user_projects add column if not exists updated_at timestamptz not null default now();

create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_user_projects_updated_at on public.user_projects;
create trigger trg_user_projects_updated_at
before update on public.user_projects
for each row execute function public.set_updated_at();
