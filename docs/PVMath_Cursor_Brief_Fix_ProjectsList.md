# Cursor Brief — Fix "Could not list projects" / save-reload failure

**Requested by:** Mohammed Ismail Pasha, 2026-06-27
**Symptom:** My Projects page shows a red "Could not list projects" banner and "No projects yet," even after saving. Projects can't be reopened.

## Root cause (high confidence, from code — verify the one DB check below before applying)

`api/routers/projects.py` → `list_projects()` (line 96) asks Supabase/PostgREST to sort by:
```
order: "updated_at.desc.nullslast,created_at.desc"
```
and `api/schemas/projects.py`'s `ProjectRecord` model (lines 26-27) declares `created_at` / `updated_at` as fields the API expects back from every row.

But the only migration that ever touched `user_projects` — `supabase_migration_multi_project.sql` — only adds an `id` column. It never added `created_at` or `updated_at`. If those columns don't actually exist on the table, PostgREST rejects the `order=` clause with a 400, and `list_projects()` (line 100-101) swallows that real error and just raises a generic `"Could not list projects"` — which is exactly the text in the screenshot. Every other write endpoint in that file (`create_project`, `update_project`, etc.) uses `_supabase_error_detail()` to surface the *real* Postgrest message; `list_projects` is the one place that doesn't, which is why the actual cause got hidden.

**One-time check before running the fix:** open the Supabase Table Editor → `user_projects` → confirm `created_at` and `updated_at` columns are missing. If they're already there, the cause is different (likely an RLS policy blocking the authenticated `SELECT`) — message back rather than running the migration blind.

## Fix

### 1. Add the missing columns + auto-update trigger (Supabase SQL editor)
```sql
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
```

### 2. Stop swallowing the real error (`api/routers/projects.py`, `list_projects`, lines 100-101)
Replace:
```python
if r.status_code != 200:
    raise HTTPException(status_code=500, detail="Could not list projects")
```
with:
```python
if r.status_code != 200:
    raise HTTPException(status_code=500, detail=_supabase_error_detail(r, "Could not list projects"))
```
This makes any future schema/RLS mismatch on this endpoint show the actual Postgrest message in the UI instead of a dead end.

## Verify after deploying
1. Run the SQL migration in Supabase.
2. Deploy the `list_projects` change.
3. Reload My Projects — saved projects should now list and reopen.
4. Save a new project, confirm it appears with a real date instead of a blank one.
