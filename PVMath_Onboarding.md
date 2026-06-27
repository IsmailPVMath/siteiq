# PVMath Onboarding

Read this in 15 minutes, then go build. For full depth on anything here, see `PVMath_Master_Context.md`.

## What this is

PVMath-Solar Site Intelligence Platform — a solar site intelligence platform for **ground-mount solar only** (Fixed Tilt + Single-Axis Tracker, Standard + Agri-PV). Three modules are live: **SiteIQ** (site screening), **TerrainIQ** (terrain/DEM export), **YieldIQ** (preliminary yield). A fourth, **LayoutIQ** (auto layout + BOM), is built but admin-only.

Solo founder (Mohammed Ismail Pasha, a working solar engineer, not a coder) builds this entirely through Claude. Started 2026-06-11 — moves fast, ships daily.

## Stack in one paragraph

Single Streamlit Python app (`app.py` + `pages/*.py`), no separate backend — server-rendered, stateful via `st.session_state`. Auth/DB via Supabase REST (raw `requests`, no SDK). External data from PVGIS (solar), OpenTopoData/Copernicus GLO-30 (terrain), Nominatim (geocoding). PDFs via ReportLab. Hosted on Railway (`siteiq.pvmath.com` + `topoiq.pvmath.com`, same deployment, two domains). Marketing site is a separate static `index.html` on GitHub Pages.

## Get oriented in the code

1. `app.py` — entrypoint: auth gate, hidden native nav + hand-built sidebar, bfcache/token-refresh fixes. Read this first.
2. `pages/project.py` — where users set up a project; the hub that hands off to every module.
3. `pages/siteiq.py`, `pages/terrainiq.py`, `pages/yieldiq.py` — the three live modules. Each is self-contained (~1,100–1,500 lines): fetch data → compute → render → build PDF.
4. `pages/_layoutiq.py` — admin-only (leading underscore hides it from nav; gated by `_ADMIN` emails in `app.py`).
5. `pvmath_auth.py` — all auth, usage limits, project CRUD, Stripe link, OTP email.
6. `pvmath_styles.py` — shared CSS injected on every page via `inject_styles()`.

Dead code, ignore: root-level `terrainiq.py`, `usage_tracker.py` (superseded, not imported anywhere).

## The 8 things you must never break

These are each a fix for a real bug that has already happened once:

1. The bfcache reload script at the top of `app.py` (fixes ghost pages on browser Back).
2. The hand-built sidebar + `st.navigation(..., position="hidden")` (native Streamlit nav had contrast/cross-browser bugs).
3. `st.query_params["s"]` reasserted as the literal last line of every `app.py` run (Streamlit's router strips query params on nav — this is how the Supabase refresh token survives).
4. Nominatim User-Agent string `"SiteIQ/1.0 (pvmath.com; contact@pvmath.com)"` (generic UA gets blocked).
5. Terrain dataset switch is lat/lon bounding-box only (`eudem25m` Europe / `srtm30m` global) — don't make it `project_country`-based, that's a different function's rule.
6. `assess_eeg()` prioritizes `project_country` text over lat/lon (opposite rule from #5 — don't unify them).
7. No hardcoded prices in app UI — pricing lives only on the website and is deferred to Stripe once that's wired up.
8. Every ReportLab PDF table cell is wrapped in `Paragraph` (plain strings don't wrap), and zero emoji in PDFs (renders as black squares).

## Git workflow

```bash
cd ~/Desktop/solarscout
git checkout staging
# make changes
git add -A && git commit -m "..." && git push origin staging
git checkout main
git merge staging -m "..."
git push origin main      # Railway auto-deploys from main
git checkout staging
```

**If you're an AI agent working from a sandbox:** you cannot push or fetch to GitHub at all (proxy blocks it — confirmed both directions). And sandbox-side `git commit` leaves real lock files (`.git/HEAD.lock`, `tmp_obj_*`) on the owner's actual filesystem that block their next local git command, because the sandbox can't clean up after itself. Prefer asking the owner to run git commands locally. If you must commit from a sandbox, warn them they may need to `rm -f .git/HEAD.lock .git/index.lock` before their next command, and always verify a push landed by asking them to paste local `git log` output — never trust sandbox output for remote state.

## Where things live

- **Railway:** one service, two domains (siteiq.pvmath.com, topoiq.pvmath.com), env vars `SUPABASE_URL`, `SUPABASE_KEY`, `BREVO_API_KEY`, SMTP fallback vars.
- **DNS:** Namecheap, A records → GitHub Pages (website), CNAMEs → Railway (app).
- **Secrets:** `.streamlit/secrets.toml` is local-dev-only and gitignored. Production reads `os.environ` only — checked before `st.secrets` everywhere.
- **Stripe:** not live yet — `STRIPE_LINK` in `pvmath_auth.py` is still a placeholder.
- **Brevo OTP:** disabled pending account activation; signup currently auto-logs users in instead.

## Current pricing (changes often — verify against `index.html` before quoting it)

Free (5/module/mo) · Professional €199/mo (50/module/mo) · Developer €799/mo (250/module/mo, 5 seats) · Enterprise custom.

## Known open issues

- YieldIQ's website card has a stale CSS class (`"soon"` with "Live Now" text) — cosmetic, safe to fix.
- `PVMath_Launch_Business_Guide.docx` exists but hasn't been read into context yet.
- Whether RevenueIQ/ProcureIQ/FieldIQ (named in the old root `CLAUDE.md` roadmap) are still planned is unconfirmed — they don't exist in current code.

## Before you touch anything risky

Auth, deployment, pricing, or any of the 8 rules above — say what you're about to change and why before doing it. These are exactly the areas with a history of real regressions.
