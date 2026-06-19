-- Site Screening Library — persistent SiteIQ results + anonymized benchmarking RPC
-- Run in Supabase SQL editor after deploying app code that calls save_site_screening_result().

create table if not exists public.site_screening_library (
    id                      uuid primary key default gen_random_uuid(),
    user_id                 uuid not null,
    project_name            text,
    created_at              timestamptz not null default now(),
    country                 text,
    region_state            text,
    latitude                double precision,
    longitude               double precision,
    site_area_ha            double precision,
    land_use_type           text,
    mounting_system         text,
    ghi_kwh_m2_yr           double precision,
    poa_kwh_m2_yr           double precision,
    specific_yield_kwh_kwp_yr double precision,
    estimated_capacity_min_mwp double precision,
    estimated_capacity_max_mwp double precision,
    estimated_output_min_mwh_yr double precision,
    estimated_output_max_mwh_yr double precision,
    max_slope_percent       double precision,
    mean_slope_percent      double precision,
    slope_confidence        text,
    flood_risk_label        text,
    flood_confidence        text,
    solar_resource_score    integer,
    terrain_score           integer,
    flood_risk_score        integer,
    land_use_score          integer,
    grid_regulatory_score   integer,
    pvmath_score            integer,
    verdict_label           text,
    module_confidence       text,
    data_sources_used       text,
    report_id               uuid unique default gen_random_uuid(),
    report_pdf_url          text,
    raw_inputs_json         jsonb,
    raw_outputs_json        jsonb
);

create index if not exists site_screening_library_user_id_idx
    on public.site_screening_library (user_id, created_at desc);

create index if not exists site_screening_library_country_idx
    on public.site_screening_library (country);

create index if not exists site_screening_library_pvmath_score_idx
    on public.site_screening_library (pvmath_score);

alter table public.site_screening_library enable row level security;

-- Users may insert their own screenings (user_id must match JWT subject).
drop policy if exists site_screening_library_insert_own on public.site_screening_library;
create policy site_screening_library_insert_own
    on public.site_screening_library for insert
    to authenticated
    with check (auth.uid() = user_id);

-- Users may read only their own history.
drop policy if exists site_screening_library_select_own on public.site_screening_library;
create policy site_screening_library_select_own
    on public.site_screening_library for select
    to authenticated
    using (auth.uid() = user_id);

-- Anonymized benchmark aggregates — no row-level data exposed.
create or replace function public.get_screening_benchmark_stats(
    p_pvmath_score integer,
    p_country text default null
)
returns json
language plpgsql
security definer
set search_path = public
as $$
declare
    v_global_count integer;
    v_country_count integer;
    v_global_avg numeric;
    v_top_q numeric;
    v_global_pct numeric;
    v_country_pct numeric;
begin
    select count(*)::integer, coalesce(avg(pvmath_score), 0)
    into v_global_count, v_global_avg
    from site_screening_library
    where pvmath_score is not null;

    select percentile_cont(0.75) within group (order by pvmath_score)
    into v_top_q
    from site_screening_library
    where pvmath_score is not null;

    if v_global_count >= 50 and p_pvmath_score is not null then
        select (count(*) filter (where pvmath_score < p_pvmath_score)::numeric
                + 0.5 * count(*) filter (where pvmath_score = p_pvmath_score)::numeric)
               / greatest(v_global_count, 1) * 100
        into v_global_pct
        from site_screening_library
        where pvmath_score is not null;
    else
        v_global_pct := null;
    end if;

    if p_country is not null and trim(p_country) <> '' then
        select count(*)::integer
        into v_country_count
        from site_screening_library
        where pvmath_score is not null
          and lower(country) = lower(trim(p_country));

        if v_country_count >= 20 and p_pvmath_score is not null then
            select (count(*) filter (where pvmath_score < p_pvmath_score)::numeric
                    + 0.5 * count(*) filter (where pvmath_score = p_pvmath_score)::numeric)
                   / greatest(v_country_count, 1) * 100
            into v_country_pct
            from site_screening_library
            where pvmath_score is not null
              and lower(country) = lower(trim(p_country));
        else
            v_country_pct := null;
        end if;
    else
        v_country_count := 0;
        v_country_pct := null;
    end if;

    return json_build_object(
        'global_count', v_global_count,
        'global_percentile', v_global_pct,
        'global_average', round(v_global_avg::numeric, 1),
        'top_quartile_threshold', round(v_top_q::numeric, 1),
        'country_count', coalesce(v_country_count, 0),
        'country_percentile', v_country_pct,
        'benchmark_ready', (v_global_count >= 50)
    );
end;
$$;

revoke all on function public.get_screening_benchmark_stats(integer, text) from public;
grant execute on function public.get_screening_benchmark_stats(integer, text) to authenticated;
