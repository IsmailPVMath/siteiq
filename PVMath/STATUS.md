# PVMath — Current Status

**Last updated:** 27 June 2026  
**Read this first** when starting a new Cursor session. Then `CLAUDE.md` for deeper technical history (some sections are Streamlit-era — this file takes precedence for architecture and pricing).

---

## One-line summary

**Unified SiteIQ Platform** at **app.pvmath.com** (React + FastAPI): one guided workflow from coordinates/boundary through screening, terrain, layout, and yield. **Per-project analysis billing** (10 / 50 / 250 / unlimited per month). **Stripe not live** — manual Supabase activation. **Streamlit legacy** (`siteiq` / `topoiq` subdomains) still in repo; primary product is the React app.

---

## Business & legal

| Item | Status |
|------|--------|
| Legal form | **Einzelunternehmen** (Mohammed Ismail Pasha, trading as PVMath) — registering |
| Steuerberater | Approved sole prop + personal bank account for payments |
| UG (haftungsbeschränkt) | **Deferred** — new Stripe account when UG formed later |
| Gewerbe Regensburg | **TODO** |
| Steuernummer / USt-IdNr | **TODO** — after Finanzamt (USt-IdNr often 1–3 weeks) |
| Ideematec Nebentätigkeit | Confirm / disclose if contract requires |
| IHK | Automatic after Gewerbe — pay when billed |

**Public legal pages:** `impressum.html`, `privacy.html`, `terms.html` — updated for app.pvmath.com + per-project usage.  
**Docs:** `docs/PVMath_Einzelunternehmen_Launch_Plan.docx` · `PVMath/README.md` (Founder Handbook)

---

## Product (what’s live)

| Asset | URL | Host | Status |
|-------|-----|------|--------|
| **SiteIQ Platform (primary)** | [app.pvmath.com](https://app.pvmath.com) | Cloudflare Pages (`frontend/`) | ✅ Production |
| **API** | [api.pvmath.com](https://api.pvmath.com) | Railway (`api/`, FastAPI) | ✅ Production |
| **Marketing site** | [pvmath.com](https://pvmath.com) | GitHub Pages (`index.html` on `main`) | ✅ Production |
| Streamlit (legacy) | siteiq.pvmath.com, topoiq.pvmath.com | Railway (`app.py`) | ⚠️ Retained — not primary; retire when comfortable |

### Unified workflow (React)

Five connected steps in one app — **one login, one project context**:

1. **Project Setup** — Quick Mode (coordinates / address) or Full Mode (draw or upload boundary)
2. **SiteIQ** — PVGIS solar, OSM grid, flood heuristic, regulatory pointers, GIS setbacks, capacity
3. **TerrainIQ** — Region-routed DEM slope analysis, heatmaps, 3D terrain preview
4. **LayoutIQ** — Mount type (fixed tilt / SAT) chosen here; auto row packing, GCR sweep, 3D layout on terrain
5. **YieldIQ** — PVGIS yield; auto-runs when user proceeds to this step

**Exports:** PDF reports, project ZIP, DXF + LandXML (terrain), layout GeoJSON. No GLB export (3D viewer only).

### Data sources (current)

| Data | Source |
|------|--------|
| Solar / yield | PVGIS (JRC) |
| Terrain DEM | **Region-routed:** Copernicus EEA-10 (EU), USGS 3DEP (USA), FABDEM (global), GLO-30 fallback — see `pvmath_terrain_sources.py` |
| Geocoding | Nominatim / OSM |
| Constraints | OSM layers (roads, water, buildings, etc.) |

### Deploy wiring

| Environment | Git branch | Host |
|-------------|------------|------|
| Production API | `main` | Railway `exemplary-balance` |
| Staging API | `staging` | Railway `cozy-enjoyment` |
| React app | `main` | Cloudflare Pages — build: `cd frontend && npm ci && npm run build`, output: `frontend/dist`, env: `VITE_API_URL=https://api.pvmath.com` |
| Marketing | `main` | GitHub Pages |

**Latest production commit:** `2c6be7d` — *Redesign marketing site to match React platform workflow.*

Recent stack (newest first): `be7a53a` per-project pricing + legal · `3fbd72a` save fixes, mount in LayoutIQ, auto YieldIQ · `ebc39bd` app.pvmath.com CORS.

---

## Pricing & billing

**Model:** One **project analysis** = one SiteIQ screening run. TerrainIQ, LayoutIQ, and YieldIQ on the same project in the same month do **not** consume extra credits.

| Plan | Price | Limit |
|------|-------|-------|
| Free | €0 | **10** project analyses / month |
| Professional | €149/mo | **50** project analyses / month |
| Developer | €499/mo | **250** project analyses / month, **5 team seats** (shared pool) |
| Enterprise | Custom | **Unlimited** |

| Billing piece | Status |
|---------------|--------|
| Usage counter | `usage_tracking.app = 'platform'` — enforced in `pvmath_supabase.py` / `pvmath_auth.py` |
| Credit charged on | SiteIQ screen only (`api/routers/workflow.py`, `gate.py`) — not on TopoIQ/YieldIQ |
| Stripe account | **Not opened yet** |
| Website **Subscribe** | Still → `#contact` (Formspree) — wire Stripe Payment Links when ready |
| Manual activation | Supabase SQL — `docs/PVMath_Manual_Billing_Runbook.md` |
| Stripe webhooks → auto `profiles.plan` | **Not built** |
| Developer team invites | ✅ Live — Manage membership → Team (`pvmath_team.py`) |

---

## App UX (recent — React)

- **Auth** — login, create account, forgot password at app.pvmath.com (no admin default email)
- **Project save/load** — partial `PATCH` updates to avoid timeout on second save; MultiPolygon boundaries
- **GIS setbacks** — editable table updates map + buildable area; cached OSM layers
- **Mount type** — selected in **LayoutIQ**, not Project Setup (SiteIQ / TerrainIQ are mount-agnostic)
- **YieldIQ** — runs automatically when proceeding to Yield step
- **3D terrain** — viewer with fixed-tilt legs + axis gizmo; GLB export removed from UI
- **Tab title** — project name + location in workflow; `SiteIQ by PVMath` on auth/setup
- **Account sidebar** — shows project analyses used (pooled `platform` counter)
- **Settings / Manage membership** — name, plan, team invites, upgrade contact

---

## Architecture (for new sessions)

```
pvmath.com (static)          app.pvmath.com (React/Vite)
        │                              │
        └──────────────┬───────────────┘
                       ▼
              api.pvmath.com (FastAPI)
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
    Supabase      PVGIS/OSM     Region DEM
    auth/DB       Nominatim     EEA-10/3DEP/FABDEM
```

| Layer | Key paths |
|-------|-----------|
| React UI | `frontend/src/` — `App.tsx`, `pages/OutputPage.tsx`, `pages/ProjectSetupPage.tsx` |
| API | `api/main.py`, `api/routers/workflow.py`, `projects.py`, `topoiq.py`, `yieldiq.py` |
| Shared logic | `pvmath_workflow/`, `layoutiq/`, `pvmath_gate/`, `pvmath_terrain_sources.py` |
| Auth / usage | `pvmath_supabase.py` (API), `pvmath_auth.py` (Streamlit legacy) |
| Marketing + legal | `index.html`, `impressum.html`, `privacy.html`, `terms.html` |
| Streamlit legacy | `app.py`, `pages/*.py` — parallel deployment, not the primary UX |

---

## Immediate next steps (priority order)

1. [ ] **Stripe** — Einzelunternehmer account + Payment Links (Pro €149, Dev €499)
2. [ ] Wire **index.html** Subscribe + in-app upgrade → Stripe; keep manual runbook as fallback
3. [ ] **Gewerbe** + Steuernummer / USt-IdNr — update impressum when received
4. [ ] (Optional) Supabase Edge Function **stripe-webhook** for auto plan activation
5. [ ] **Retire Streamlit** from production Railway when React is fully validated — redirect siteiq/topoiq → app.pvmath.com
6. [ ] Keep **`PVMath/STATUS.md`** updated after each milestone (2 min)

---

## Key files (quick index)

| Topic | Path |
|-------|------|
| **This file** | `PVMath/STATUS.md` |
| AI project memory (long) | `CLAUDE.md` |
| Founder Handbook | `PVMath/README.md` |
| Manual billing | `docs/PVMath_Manual_Billing_Runbook.md` |
| Usage limits | `pvmath_supabase.py` — `PLAN_LIMITS`, `PLATFORM_APP`, `usage_limit_detail()` |
| React API client | `frontend/src/lib/api.ts`, `frontend/src/lib/workflowSave.ts` |
| Workflow types / pipeline | `frontend/src/types/workflow.ts` |
| Cloudflare Pages config | `wrangler.toml`, `frontend/.env.example` |
| Team invites | `pvmath_team.py`, `supabase_migration_team_invites.sql` |
| Terrain routing | `pvmath_terrain_sources.py` |
| Layout engine | `layoutiq/engine.py` |

---

## How to resume in Cursor

Paste as your first message:

```
Continue PVMath. Read PVMath/STATUS.md and CLAUDE.md first.
git log -5 on main. Next task: [describe what you want].
```

Or reopen a prior chat thread (Cursor keeps history).

---

## Update rule

When something material changes (Stripe live, Gewerbe done, Streamlit retired, first paying customer), **edit this file first** — update the one-line summary, pricing table, or next steps. Takes 2 minutes; saves re-explaining everything in every new session.
