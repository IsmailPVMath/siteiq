# PVMath / SiteIQ — Project Context

Paste this file (or point Claude at it) at the start of every coding session.
This is the single source of truth for how the app is built, deployed, and what is/isn't safe to touch.
(`CLAUDE.md` in this same folder is the long-form version with full feature logic and bug history — this file is the short operational checklist.)

---

## 1. What this is

**SiteIQ by PVMath** — Solar Site Intelligence Platform for ground-mount solar (Fixed Tilt + Single-Axis Tracker, Standard + Agri-PV). No rooftop/carport/floating/BIPV.

Owner: Mohammed Ismail Pasha (ismailpasha747@gmail.com) — solo founder, side project alongside a full-time solar engineering job. **Does not write code directly — all changes are made by Claude.** That makes process discipline (this file) more important than usual, not less.

---

## 2. Deployment — read this before touching anything deployment-related

- **Hosting: Railway.** NOT Streamlit Community Cloud (migrated away — Streamlit Cloud can't do a true custom top-level domain).
- Start command (`railway.toml`): `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`
- Healthcheck path: `/_stcore/health`
- Auto-deploys on every push to `main` on GitHub (`IsmailPVMath/siteiq`). **There is currently no staging environment — every push to `main` goes straight to the live app real users are on.** Treat `main` accordingly until a staging Railway service + branch exists.
- Live URLs: `https://siteiq.pvmath.com`, `https://topoiq.pvmath.com` (same Railway deployment, two custom domains via Railway-terminated CNAMEs — no redirect/proxy in between).
- Domain registrar: Namecheap. Website `pvmath.com` is a *separate* deploy — GitHub Pages serving `index.html` from the repo root, unrelated to Railway.

### Required environment variables (Railway → Variables)
| Variable | Used for |
|---|---|
| `SUPABASE_URL` | Auth + DB (`pvmath_auth.py`) |
| `SUPABASE_KEY` | Auth + DB (`pvmath_auth.py`) |
| `BREVO_API_KEY` | OTP/notification email (Brevo HTTP API) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` | SMTP fallback for local/dev email |

`STRIPE_LINK` is **not** an env var — it's a hardcoded constant in `pvmath_auth.py`, currently still the placeholder `https://buy.stripe.com/YOUR_LINK_HERE`. Needs a real Stripe Customer Portal link before "Manage Membership" actually works.

### Deploy commands (run on your own Mac — Claude's sandbox cannot push)
```bash
cd ~/Desktop/solarscout
rm -f .git/index.lock .git/HEAD.lock   # only if a previous commit got interrupted
git add -A
git commit -m "describe the change"
git push origin main
```

---

## 3. Modules — actual current state (per app.py's registered pages, not aspirational)

| Page | File | Status |
|---|---|---|
| Overview | `pages/overview.py` | Live |
| Project (setup) | `pages/project.py` | Live |
| My Projects | `pages/my_projects.py` | Live |
| **SiteIQ** | `pages/siteiq.py` | Live — site screening (solar/terrain/flood/regulatory/capacity + PDF) |
| **TopoIQ** | `pages/topoiq.py` | Live — terrain/slope analysis + PDF |
| **YieldIQ** | `pages/yieldiq.py` | Live — yield workflow |
| LayoutIQ | `pages/_layoutiq.py` | **Admin-only, in progress.** Leading underscore = intentionally not in the nav list for normal users; only appended for emails in `_ADMIN` (currently just the owner's). Not ready for public users. |

Root-level `topoiq.py` and `usage_tracker.py` are **dead code** — not imported/registered anywhere. Do not edit them expecting it to affect the live app; if cleaning up, confirm dead-ness again first since this can change.

**Launch sequencing rule (do not violate without an explicit decision):** modules go live to real users one at a time, only once stable — SiteIQ first, then TopoIQ, then YieldIQ. Do not flip a new module from admin-only to public in the same change as unrelated fixes.

---

## 4. Tech stack

- Framework: Streamlit (Python), multi-page via `st.navigation(_pages, position="hidden")` + a hand-built sidebar in `app.py` (Streamlit's own nav UI is not used — see §5).
- Maps: streamlit-folium + folium
- Geocoding: Nominatim/OSM, User-Agent `"SiteIQ/1.0 (pvmath.com; contact@pvmath.com)"` — do not revert to a generic UA, Nominatim will start blocking requests again.
- Solar data: EU PVGIS API (JRC)
- Terrain data: OpenTopoData — `eudem25m` for Europe (34–72°N, −25–45°E), `srtm30m` globally. Dataset choice is by lat/lon, not by `project_country` text.
- PDF: ReportLab — every table cell must be wrapped in a `Paragraph` object (plain strings don't wrap and overflow the page).
- Auth/DB: Supabase (email/password, REST API via `pvmath_auth.py` — no `supabase-py` SDK used despite it being in `requirements.txt`)
- Email: Brevo HTTP API, SMTP fallback for local dev

---

## 5. What must never be changed without an explicit, separate conversation about it

These are fixes for bugs that have already happened once — reverting them silently as a side effect of an unrelated change has caused real regressions before.

1. **The bfcache reload script at the top of `app.py`** (`components.html(...)` with the `pageshow`/`event.persisted` listener). Removing it brings back "sidebar vanishes on browser Back/Refresh."
2. **The hand-built sidebar in `app.py`** (`with st.sidebar:` block) and the fact that `st.navigation(..., position="hidden")` hides Streamlit's own nav UI. Don't reintroduce Streamlit's native sidebar nav or its native collapse control — it was removed because it was low-contrast and inconsistent across versions, and because Streamlit can strip query params on transition (see #3).
3. **`st.query_params["s"]` re-assertion as the last line of every `app.py` run**, restoring the Supabase refresh token. Streamlit's multipage navigation can silently strip URL params on page transitions; this line is what stops every refresh from logging the user out. Do not remove or move it earlier in the script.
4. **Nominatim User-Agent string** in geocoding calls — must stay `"SiteIQ/1.0 (pvmath.com; contact@pvmath.com)"`.
5. **The terrain dataset switch** (`eudem25m` vs `srtm30m` by lat/lon bounding box) — needed for the app to work outside Europe.
6. **`assess_eeg()`'s `project_country`-first, lat/lon-fallback priority** — without it, non-DACH projects show German regulatory authorities.
7. **No hardcoded prices in user-facing CTAs.** Plan/price/upgrade-path display is deferred to the Stripe Customer Portal once `STRIPE_LINK` is real — don't reintroduce a `PRICE_LABEL` constant into visible UI.
8. **PDF cell wrapping (`Paragraph`, not plain strings) and no emoji in ReportLab output** (renders as black squares).

---

## 6. Known bugs / open items

- `STRIPE_LINK` in `pvmath_auth.py` is still a placeholder — "Manage Membership" doesn't yet show a real plan or upgrade path. Needs the owner's Stripe account access to fix; Claude cannot do this part.
- No staging environment exists yet — every `main` push is a production deploy (see §2).
- Sidebar-vanishes-on-back/refresh fix (the bfcache reload script, §5.1) was just added and is **not yet confirmed working in production** — pending push + a real Safari back/refresh test on the live site.
- Git lock files (`.git/index.lock`, `.git/HEAD.lock`) have repeatedly reappeared in Claude's sandbox and block commits there; the sandbox also cannot reach GitHub to push (proxy blocks it with a 403). **All git commit/push operations for this project must be run by the owner on their own Mac**, not assumed to have happened from inside a Claude session.

## 7. Recently fixed (so they don't get "fixed" again from scratch)

- TopoIQ PDF slope map was stretched/cropped ("inverted map") — fixed by sizing the embedded image from its real PIL pixel aspect ratio instead of a hardcoded ratio.
- TopoIQ PDF now includes a Slope Distribution table (0–2.5% / 2.5–5% / 5–7.5% / 7.5–10% / >10% of site area).
- Sidebar "Signed in as" email and the Settings panel text were low-contrast/inconsistent — now plain white, matching the rest of the sidebar.
- A buggy overlapping "Upgrade to Pro — €49/month" tooltip was removed (price was stale anyway — see §5.7).

---

## 8. How to ask Claude for changes (process, not just content)

- Say which file(s) the change should touch. If you don't know, ask Claude to find the file first as a separate step, confirm it with you, *then* make the change.
- For a bug report: "Only inspect `<file>` and identify the cause. Do not change anything yet" — get a diagnosis before a fix.
- For a fix: ask for a `py_compile` check (or equivalent) after every edit, and a one-line summary of exactly what changed and why.
- Before any change that touches deployment, auth, or anything in §5, ask Claude to point out if it conflicts with this file.
- After any session, update §6/§7 above before closing — this file is only useful if it stays current.
