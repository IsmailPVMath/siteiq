-- PVMath — Developer team invites (up to 5 seats, shared usage pool)
-- Run once in Supabase SQL Editor after supabase_migration_plan_limits.sql.
--
-- Enables in-app team invites without manual Supabase SQL for each teammate.
-- Owner: plan = developer, team_id IS NULL
-- Member: plan = developer, team_id = owner's user id

-- ── Invites table ────────────────────────────────────────────────────────────
create table if not exists public.team_invites (
    id            uuid primary key default gen_random_uuid(),
    owner_id      uuid not null references public.profiles (id) on delete cascade,
    invitee_email text not null,
    token         text not null unique default encode(gen_random_bytes(24), 'hex'),
    status        text not null default 'pending'
                  check (status in ('pending', 'accepted', 'revoked', 'expired')),
    created_at    timestamptz not null default now(),
    expires_at    timestamptz not null default (now() + interval '14 days'),
    accepted_at   timestamptz
);

create index if not exists team_invites_owner_idx on public.team_invites (owner_id);
create index if not exists team_invites_email_idx on public.team_invites (lower(invitee_email));

create unique index if not exists team_invites_pending_owner_email_uniq
    on public.team_invites (owner_id, lower(invitee_email))
    where status = 'pending';

alter table public.team_invites enable row level security;

drop policy if exists "team_invites_owner_select" on public.team_invites;
create policy "team_invites_owner_select"
    on public.team_invites for select
    using (owner_id = auth.uid());

drop policy if exists "team_invites_owner_update" on public.team_invites;
create policy "team_invites_owner_update"
    on public.team_invites for update
    using (owner_id = auth.uid())
    with check (owner_id = auth.uid());

-- Inserts go through create_team_invite() RPC (validates seats + plan).

-- ── Helpers ──────────────────────────────────────────────────────────────────
create or replace function public._team_owner_id(p_user_id uuid)
returns uuid
language sql
stable
security definer
set search_path = public
as $$
    select coalesce(p.team_id, p.id)
    from public.profiles p
    where p.id = p_user_id
      and p.plan = 'developer';
$$;

create or replace function public._team_occupied_seats(p_owner_id uuid)
returns integer
language sql
stable
security definer
set search_path = public
as $$
    select 1 + count(*)::integer
    from public.profiles
    where team_id = p_owner_id;
$$;

-- ── RPC: create invite ───────────────────────────────────────────────────────
create or replace function public.create_team_invite(p_email text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_uid       uuid := auth.uid();
    v_plan      text;
    v_team_id   uuid;
    v_email     text := lower(trim(p_email));
    v_occupied  integer;
    v_invite_id uuid;
    v_token     text;
begin
    if v_uid is null then
        raise exception 'Not signed in.';
    end if;

    select plan, team_id into v_plan, v_team_id
    from public.profiles where id = v_uid;

    if v_plan is distinct from 'developer' or v_team_id is not null then
        raise exception 'Only the Developer plan team owner can send invites.';
    end if;

    if v_email is null or v_email !~ '^[^@]+@[^@]+\.[^@]+$' then
        raise exception 'Enter a valid email address.';
    end if;

    v_occupied := public._team_occupied_seats(v_uid);
    if v_occupied >= 5 then
        raise exception 'Team is full (5 seats including you).';
    end if;

    if exists (
        select 1
        from auth.users u
        join public.profiles p on p.id = u.id
        where lower(u.email) = v_email
          and (p.id = v_uid or p.team_id = v_uid)
    ) then
        raise exception 'That user is already on your team.';
    end if;

    update public.team_invites
       set status = 'revoked'
     where owner_id = v_uid
       and lower(invitee_email) = v_email
       and status = 'pending';

    insert into public.team_invites (owner_id, invitee_email)
    values (v_uid, v_email)
    returning id, token into v_invite_id, v_token;

    return jsonb_build_object(
        'id', v_invite_id,
        'token', v_token,
        'invitee_email', v_email
    );
end;
$$;

-- ── RPC: accept invite ───────────────────────────────────────────────────────
create or replace function public.accept_team_invite(p_token text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_uid         uuid := auth.uid();
    v_email       text;
    v_invite      public.team_invites%rowtype;
    v_occupied    integer;
begin
    if v_uid is null then
        raise exception 'Not signed in.';
    end if;

    select lower(email) into v_email from auth.users where id = v_uid;

    select * into v_invite
    from public.team_invites
    where token = trim(p_token)
      and status = 'pending'
      and expires_at > now()
    limit 1;

    if not found then
        raise exception 'Invite not found or expired.';
    end if;

    if v_invite.invitee_email is distinct from v_email then
        raise exception 'This invite was sent to a different email. Sign in with %.', v_invite.invitee_email;
    end if;

    if exists (
        select 1 from public.profiles
        where id = v_uid and plan = 'developer'
    ) then
        raise exception 'You are already on a Developer plan team.';
    end if;

    v_occupied := public._team_occupied_seats(v_invite.owner_id);
    if v_occupied >= 5 then
        raise exception 'That team is full.';
    end if;

    update public.profiles
       set plan = 'developer',
           team_id = v_invite.owner_id
     where id = v_uid;

    update public.team_invites
       set status = 'accepted',
           accepted_at = now()
     where id = v_invite.id;

    return jsonb_build_object('owner_id', v_invite.owner_id);
end;
$$;

-- ── RPC: roster ──────────────────────────────────────────────────────────────
create or replace function public.list_team_roster()
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_uid      uuid := auth.uid();
    v_owner_id uuid;
    v_plan     text;
begin
    if v_uid is null then
        return '[]'::jsonb;
    end if;

    select plan, public._team_owner_id(v_uid) into v_plan, v_owner_id
    from public.profiles where id = v_uid;

    if v_plan is distinct from 'developer' or v_owner_id is null then
        return '[]'::jsonb;
    end if;

    return coalesce((
        select jsonb_agg(row_to_json(t) order by t.role desc, t.email)
        from (
            select
                p.id,
                lower(u.email) as email,
                coalesce(
                    nullif(trim(u.raw_user_meta_data->>'full_name'), ''),
                    nullif(trim(concat(
                        u.raw_user_meta_data->>'first_name', ' ',
                        u.raw_user_meta_data->>'last_name'
                    )), ''),
                    lower(u.email)
                ) as display_name,
                case when p.id = v_owner_id then 'owner' else 'member' end as role
            from public.profiles p
            join auth.users u on u.id = p.id
            where p.id = v_owner_id or p.team_id = v_owner_id
        ) t
    ), '[]'::jsonb);
end;
$$;

-- ── RPC: pending invites (owner only) ───────────────────────────────────────
create or replace function public.list_team_invites()
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_uid uuid := auth.uid();
begin
    if v_uid is null then
        return '[]'::jsonb;
    end if;

    if not exists (
        select 1 from public.profiles
        where id = v_uid and plan = 'developer' and team_id is null
    ) then
        return '[]'::jsonb;
    end if;

    return coalesce((
        select jsonb_agg(row_to_json(t) order by t.created_at desc)
        from (
            select id, invitee_email, token, created_at, expires_at
            from public.team_invites
            where owner_id = v_uid
              and status = 'pending'
              and expires_at > now()
        ) t
    ), '[]'::jsonb);
end;
$$;

-- ── RPC: revoke invite ───────────────────────────────────────────────────────
create or replace function public.revoke_team_invite(p_invite_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_uid uuid := auth.uid();
begin
    if v_uid is null then
        raise exception 'Not signed in.';
    end if;

    update public.team_invites
       set status = 'revoked'
     where id = p_invite_id
       and owner_id = v_uid
       and status = 'pending';

    if not found then
        raise exception 'Invite not found.';
    end if;

    return jsonb_build_object('success', true);
end;
$$;

-- ── RPC: remove member (owner) ───────────────────────────────────────────────
create or replace function public.remove_team_member(p_member_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_uid uuid := auth.uid();
begin
    if v_uid is null then
        raise exception 'Not signed in.';
    end if;

    if p_member_id = v_uid then
        raise exception 'Use Leave team to remove yourself.';
    end if;

    if not exists (
        select 1 from public.profiles
        where id = v_uid and plan = 'developer' and team_id is null
    ) then
        raise exception 'Only the team owner can remove members.';
    end if;

    update public.profiles
       set plan = 'free',
           team_id = null
     where id = p_member_id
       and team_id = v_uid;

    if not found then
        raise exception 'Member not found on your team.';
    end if;

    return jsonb_build_object('success', true);
end;
$$;

-- ── RPC: leave team (member) ─────────────────────────────────────────────────
create or replace function public.leave_team()
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_uid     uuid := auth.uid();
    v_team_id uuid;
begin
    if v_uid is null then
        raise exception 'Not signed in.';
    end if;

    select team_id into v_team_id
    from public.profiles
    where id = v_uid and plan = 'developer' and team_id is not null;

    if v_team_id is null then
        raise exception 'You are not on a team as a member.';
    end if;

    update public.profiles
       set plan = 'free',
           team_id = null
     where id = v_uid;

    return jsonb_build_object('success', true);
end;
$$;

-- ── RPC: peek invite (for accept banner — email match only) ───────────────────
create or replace function public.peek_team_invite(p_token text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_uid   uuid := auth.uid();
    v_email text;
    v_inv   public.team_invites%rowtype;
    v_owner_email text;
begin
    if v_uid is null or coalesce(trim(p_token), '') = '' then
        return null;
    end if;

    select lower(email) into v_email from auth.users where id = v_uid;

    select * into v_inv
    from public.team_invites
    where token = trim(p_token)
      and status = 'pending'
      and expires_at > now()
    limit 1;

    if not found then
        return null;
    end if;

    if v_inv.invitee_email is distinct from v_email then
        return jsonb_build_object(
            'valid', false,
            'invitee_email', v_inv.invitee_email
        );
    end if;

    select lower(u.email) into v_owner_email
    from auth.users u where u.id = v_inv.owner_id;

    return jsonb_build_object(
        'valid', true,
        'invitee_email', v_inv.invitee_email,
        'owner_email', coalesce(v_owner_email, 'team owner')
    );
end;
$$;

grant execute on function public.create_team_invite(text) to authenticated;
grant execute on function public.accept_team_invite(text) to authenticated;
grant execute on function public.list_team_roster() to authenticated;
grant execute on function public.list_team_invites() to authenticated;
grant execute on function public.revoke_team_invite(uuid) to authenticated;
grant execute on function public.remove_team_member(uuid) to authenticated;
grant execute on function public.leave_team() to authenticated;
grant execute on function public.peek_team_invite(text) to authenticated;
