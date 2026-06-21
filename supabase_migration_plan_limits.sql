-- PVMath — plan-aware usage limits + team pooling
-- Run this once in the Supabase SQL editor (Project → SQL Editor → New query).
-- Additive only: existing columns/rows are untouched, nothing is dropped.
--
-- What this enables (see pvmath_auth.py):
--   - profiles.plan      — 'free' | 'professional' | 'developer' | 'enterprise'.
--                          Professional = 75 analyses/month POOLED across modules.
--                          Developer = 300/month POOLED (team shares one counter via usage_key).
--                          Free = 5/module.
--   - profiles.team_id   — set this to the SAME value (e.g. the paying owner's
--                          own user id) for every member of a Developer-tier
--                          team, so their usage pools against one shared
--                          Developer's 5 seats share one monthly counter instead of separate caps.
--                          Leave NULL for solo Free/Professional accounts.
--   - usage_tracking.usage_key — the id usage is actually counted against:
--                          a team_id for pooled team members, else the
--                          user's own id. Backfilled from the existing
--                          user_id column below.
--   - usage_tracking.period    — 'YYYY-MM'. Counts reset automatically each
--                          calendar month because a new period is a new row.

-- 1) profiles: add plan + team columns
alter table profiles
    add column if not exists plan text not null default 'free',
    add column if not exists team_id uuid;

-- 2) usage_tracking: add the new key + period columns
alter table usage_tracking
    add column if not exists usage_key text,
    add column if not exists period text;

-- 3) Backfill existing usage rows so old data doesn't silently disappear —
--    every row that predates this migration becomes "current period, keyed
--    by the user's own id" (nobody had a team_id before this migration existed).
update usage_tracking
   set usage_key = user_id,
       period    = to_char(now(), 'YYYY-MM')
 where usage_key is null;

-- 4) Recommended (not required to run automatically): a unique constraint so
--    increment_usage()'s "get current count, then POST or PATCH" pattern can't
--    ever create two rows for the same (usage_key, app, period) under
--    concurrent requests. Uncomment once you've confirmed no duplicate rows
--    already exist for the same key/app/period:
-- alter table usage_tracking
--     add constraint usage_tracking_key_app_period_uniq unique (usage_key, app, period);

-- 5) To put a real paying user on a plan today (until Stripe is wired):
--    update profiles set plan = 'professional' where id = '<user-uuid>';
--    update profiles set plan = 'developer'    where id = '<owner-user-uuid>';
--    -- then for each of that owner's up to 5 teammates:
--    update profiles set plan = 'developer', team_id = '<owner-user-uuid>' where id = '<teammate-uuid>';
