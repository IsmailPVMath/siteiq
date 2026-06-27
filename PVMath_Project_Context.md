# PVMath / SiteIQ — Project Context

Paste this file (or point Claude at it) at the start of every coding session.
This is the single source of truth for how the app is built, deployed, and what is/isn't safe to touch.
(`CLAUDE.md` in this same folder is the long-form version with full feature logic and bug history — this file is the short operational checklist.)

**Last updated:** 2026-06-21

---

## 1. What this is

**PVMath-Solar Site Intelligence Platform** for ground-mount solar (Fixed Tilt + Single-Axis Tracker, Standard + Agri-PV). No rooftop/carport/floating/BIPV.

Three modules are **live and public:** SiteIQ, TopoIQ, YieldIQ. LayoutIQ is **admin-only** (in progress).

Owner: Mohammed Ismail Pasha (ismailpasha747@gmail.com) — solo founder, side project alongside a full-time solar engineering job at Ideematec GmbH, Regensburg. **Does not write code directly — all changes are made by Claude/Cursor.**

---

## 2. Deployment — read this before touching anything deployment-related

- **Hosting: Railway.** NOT Streamlit Community Cloud (migrated away — Streamlit Cloud can't do a true custom top-level domain).
- Start command (`railway.toml`): `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`
- Healthcheck path: `/_stcore/health`

### Two Railway environments (staging first)

| Railway project | Git branch | Role |
|---|---|---|
| `cozy-enjoyment` | **`staging`** | Pre-production — test before promote |
| `exemplary-balance` | **`main`** | **Production** — siteiq.pvmath.com / topoiq.pvmath.com |

**Production is frozen by default.** Day-to-day fixes go to **`staging`** first; merge to **`main`** only after verification.

Live URLs: `https://siteiq.pvmath.com`, `https://topoiq.pvmath.com` (same production deployment, two custom domains via Railway-terminated CNAMEs).

Website `pvmath.com` is a **separate** deploy — GitHub Pages serving `index.html` from repo root on **`main`**.

Domain registrar: Namecheap.

### Required environment variables (Railway → Variables)
| Variable | Used for |
|---|---|
| `SUPABASE_URL` | Auth + DB (`pvmath_auth.py`) |
| `SUPABASE_KEY` | Auth + DB (`pvmath_auth.py`) |
| `BREVO_API_KEY` | OTP/notification email (Brevo HTTP API) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` | SMTP fallback for local/dev email |

`STRIPE_LINK` is **not** an env var — hardcoded in `pvmath_auth.py`, still placeholder `https://buy.stripe.com/YOUR_LINK_HERE`. Until Stripe is wired, **manual billing** applies: see `docs/PVMath_Manual_Billing_Runbook.md`.

### Deploy commands (run on your Mac)
```bash
cd ~/Desktop/solarscout
git checkout staging
# … make changes …
git add -A && git commit -m "describe the change"
git push origin staging
# → Railway staging auto-deploys — test there first

git checkout main && git pull && git merge staging && git push origin main
# → Railway production auto-deploys
```

---

## 3. Modules — actual current state

| Page | File | Status |
|---|---|---|
| Overview | `pages/overview.py` | Live — usage pool dashboard |
| Project (setup) | `pages/project.py` | Live — Quick/Full mode, pin or boundary |
| My Projects | `pages/my_projects.py` | Live |
| **SiteIQ** | `pages/siteiq.py` | Live — screening + PDF |
| **TopoIQ** | `pages/topoiq.py` | Live — terrain + CAD/PDF |
| **YieldIQ** | `pages/yieldiq.py` | Live — yield workflow + PDF |
| LayoutIQ | `pages/_layoutiq.py` | **Admin-only** — not public |

Root-level `topoiq.py` and `usage_tracker.py` are **dead code** — do not edit expecting live effect.

### Project Setup modes (`pages/project.py`)
| Mode | Map behaviour | Modules enabled |
|---|---|---|
| **Quick** | Single-click pin drop (search also drops pin) | SiteIQ, YieldIQ |
| **Full** | Draw polygon boundary (+ KMZ upload) | SiteIQ, YieldIQ, **TopoIQ** |

Pin status bar shows **resolved place name + coordinates** (same `reverse_geocode` as reports). Quick Mode copy explicitly states boundary drawing requires Full Mode.

---

## 4. Pricing & usage limits (`pvmath_auth.py`)

| Plan | Price | Limit |
|---|---|---|
| Free | €0 | **5 per module** (SiteIQ, TopoIQ, YieldIQ each) |
| Professional | **€149/mo** | **75 pooled/month** across all three modules |
| Developer | **€499/mo** | **300 pooled/month** shared team pool (5 seats) |
| Enterprise | Custom | Custom |

Website pricing cards in `index.html` match the above. Do **not** reintroduce stale €49 copy anywhere.

Manual upgrade path until Stripe: email `contact@pvmath.com` → pilot agreement + proforma → bank transfer → Supabase `profiles.plan` update (SQL in billing runbook).

Engineering Reference Manual download is gated to Professional+ (`can_download_engineering_manual()` in `pvmath_auth.py`).

---

## 5. Tech stack

- Framework: Streamlit (Python), multi-page via `st.navigation(_pages, position="hidden")` + hand-built sidebar in `app.py`
- Maps: streamlit-folium + folium; Project Setup map in `@st.fragment` (`_render_proj_map_fragment`)
- Geocoding: Nominatim/OSM — User-Agent `"SiteIQ/1.0 (pvmath.com; contact@pvmath.com)"` — **never revert**
- Solar: EU PVGIS API (JRC)
- Terrain: OpenTopoData — `eudem25m` (Europe 34–72°N, −25–45°E), `srtm30m` globally; TopoIQ also Copernicus GLO-30
- PDF: ReportLab — every table cell in `Paragraph`; **no emoji** in PDF
- Auth/DB: Supabase REST via `pvmath_auth.py` (no supabase-py SDK in use)
- Email: Brevo HTTP API, SMTP fallback for local dev

### Key helper modules
| File | Role |
|---|---|
| `pvmath_auth.py` | Auth, plans, usage limits, paywall, manual gate |
| `pvmath_geocode.py` | `reverse_geocode()`, `format_coords()` |
| `pvmath_session.py` | Project state key cleanup |
| `pvmath_help.py` | In-app ⓘ help for modules |
| **`pvmath_folium_draw.py`** | **Folium Draw contract — only entry point for draw maps** |
| `pvmath_marketing/` + `scripts/pvmath_marketing_bot.py` | LinkedIn draft generator (local) |

---

## 6. What must never be changed without an explicit conversation

1. **bfcache reload script** at top of `app.py` — removing it breaks sidebar on browser Back/Refresh
2. **Hand-built sidebar** + `st.navigation(..., position="hidden")` — don't reintroduce Streamlit native nav
3. **`st.query_params["s"]` re-assertion as last line of `app.py`** — prevents logout on refresh
4. **Nominatim User-Agent** — must stay `"SiteIQ/1.0 (pvmath.com; contact@pvmath.com)"`
5. **Terrain dataset switch** by lat/lon (`eudem25m` vs `srtm30m`)
6. **`assess_eeg()` project_country-first priority**
7. **No hardcoded stale prices in UI** — use plan-aware copy from `pvmath_auth.py`
8. **PDF: Paragraph wrapping, no emoji**
9. **Folium Draw maps** — Full Mode / TopoIQ draw must use `st_folium_with_draw()` from `pvmath_folium_draw.py` with **`last_active_drawing` only**. Never add `all_drawings` or `last_clicked` to draw-mode `returned_objects` (reruns every vertex → map remounts → 4× regression). Run `python3 scripts/check_folium_draw_regression.py` before deploy.

---

## 7. Known bugs / open items

- `STRIPE_LINK` still placeholder — "Manage Membership" not fully functional; manual billing in use
- LayoutIQ admin-only — do not expose to public without explicit decision
- Ideematec Nebentätigkeit approval pending before formal UG formation (see `docs/PVMath_UG_Formation_Guide.docx`)

---

## 8. Recently fixed (Jun 2026 — do not re-break)

- **Auth UX:** multi-word given/family names; register/settings in `st.form`; Enter submits login; Tab skips password eye icon (`pvmath_auth.py`, `app.py`)
- **Folium Draw (4× regression):** centralized in `pvmath_folium_draw.py` + `tests/test_folium_draw.py` + `scripts/check_folium_draw_regression.py`
- **Project Setup map:** single-click pin + immediate rerun; place name in status bar; Quick vs Full Mode guidance (`pages/project.py`, `pvmath_geocode.py`)
- **Pooled usage limits:** Pro 75 / Dev 300 per month (`pvmath_auth.py`, `pages/overview.py`)
- **Engineering manual:** paid-plan gate + admin caption fix
- **TopoIQ:** CAD exports with UTM georef; contour clip to boundary
- Session persistence via `pvm_refresh_token` + `?s=` URL param
- TopoIQ PDF slope map aspect ratio; slope distribution table

---

## 9. Gitignored local-only assets (do not commit)

Per `.gitignore` on `main`:
- `docs/PVMath_Engineering_Reference_Manual*.docx` — internal IP
- `scripts/manual_terms_data.py` — manual corpus source
- `marketing/drafts/*.md`, `marketing/linkedin_drafts/*.md` — regenerate with `scripts/pvmath_marketing_bot.py`
- `.DS_Store`, `.streamlit/secrets.toml`, `.env*`

---

## 10. How to ask Claude for changes

- Name target file(s) or ask for diagnosis before fixing
- Run syntax check after edits
- Staging first, then promote to `main`
- Update §7/§8 in this file when closing a session with meaningful changes
