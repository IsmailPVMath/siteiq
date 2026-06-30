# PVMath — Current Status

**Last updated:** 1 July 2026  
**Read this first** in every new Cursor session. Then `CLAUDE.md` for deeper history (**this file wins** for architecture, pricing, and what's live).

---

## One-line summary

**Unified PVMath-Solar Site Intelligence Platform** at **app.pvmath.com** (React + FastAPI): guided workflow SiteIQ → TerrainIQ → LayoutIQ → YieldIQ → Output. **Rebalanced PVMath score** (execution-weighted + regional yield + economic viability card). **Redis/RQ job queue** live on staging + production. **RevenueIQ** — screening revenue/CAPEX/payback model **in build on `staging` only** (API gated, not on website). Per-project billing 10 / 50 / 250 / unlimited. Stripe not live.

---

## Session handoff (1 Jul 2026)

**Production `main`:** `f8c5b3f` — YieldIQ mount fix, scoring rebalance, economic viability card.  
**Active dev branch:** `staging` — merge `main` + **RevenueIQ v0** (model + API, not public).

### Shipped on production (`main`, 1 Jul 2026)

| Area | What |
|------|------|
| **YieldIQ mount bug** | Compare FT & SAT → select SAT 1P no longer shows Fixed in YIQ/PDF (`pvmath_workflow/mount_utils.py`, `OutputPage.tsx`) |
| **PVMath score v2** | Weights 22/22/18/15/15/8 (reg/terrain/yield/land/flood/solar); regional yield bands; partial vs full score |
| **Economic viability** | Sidebar + PDF: engineering confidence ★, investment risk, utility-scale YES/CONDITIONAL/NO |
| **Report header** | `SiteIQ · TerrainIQ · LayoutIQ · YieldIQ` |
| **YIQ UI** | Removed Aurora/DNV/PVsyst line; cross-module ref hidden when single mount selected |
| **Job queue** | Redis + worker: `terrainiq.analyze`, `workflow.terrain_mesh`, `workflow.layout_sweep` |

### In progress on `staging` (not production / not website)

| Area | What |
|------|------|
| **RevenueIQ v0** | `revenueiq/` — tariff bands, CAPEX €/Wp, OPEX, payback, LCOE screening |
| **API** | `POST /api/v1/revenueiq/analyze` — **only when** `PVMATH_ENABLE_REVENUEIQ=1` on Railway staging |
| **UI** | Not wired yet — API-only; no `index.html` / marketing mention |
| **Next** | Staging UI step + PDF section; then score integration (~10% revenue factor) |

### Tomorrow's priorities (architecture → 1K users)

1. **Project-package job queue** — `POST /workflow/project-package-job` (biggest remaining sync/OOM risk)
2. **R2 for exports** — PDF/ZIP/DXF off API RAM
3. **Sentry** — API + React minimum monitoring
4. **RevenueIQ UI** on staging preview only (`VITE_ENABLE_REVENUEIQ=true` on Cloudflare Preview)
5. **k6 smoke** on staging — 100 VU baseline

See **`PVMath/ARCHITECTURE_ROADMAP.md`** for full CTO-ordered checklist and readiness targets.

---

## RevenueIQ (staging — private build)

**Purpose:** Screening-grade economics from existing LayoutIQ DC + YieldIQ MWh — not bankable FM.

| Input | Source |
|-------|--------|
| `dc_kwp` | Selected LayoutIQ row |
| `annual_mwh` | YieldIQ × layout DC |
| `country`, `land_use`, `mount_type` | Project setup |
| `terrain_grade` | TerrainIQ tier |

| Output | Notes |
|--------|-------|
| Revenue band €/yr | Country tariff table (`revenueiq/tariffs.py`) |
| CAPEX band € | €/Wp by mount + terrain uplift (`revenueiq/capex.py`) |
| Payback years | Simple, no discount rate |
| LCOE €/MWh | 25-yr screening headline |

**Enable on staging Railway (`cozy-enjoyment`):** set `PVMATH_ENABLE_REVENUEIQ=1` on API service.  
**Do not** set on production until promoted. **Do not** add to pvmath.com or module list on website.

**Key paths:** `revenueiq/engine.py`, `api/routers/revenueiq.py`, `tests/test_revenueiq.py`

---

## PVMath score v2 (live on main)

| Factor | Full weight | Partial (no YieldIQ) |
|--------|-------------|----------------------|
| Grid / regulatory | 22% | 30% |
| Terrain | 22% | 32% |
| Energy yield | 18% | — |
| Land use | 15% | 15% |
| Flood | 15% | 15% |
| Solar resource | 8% | 8% |

- Regional yield scoring (`pvmath_workflow/score_config.py`) — DE sites no longer stuck ~58 on yield alone
- Terrain cap: `min(weighted, terrain + 15)` still applies on challenging slopes
- Config: `pvmath_workflow/scoring.py`, tests: `tests/test_scoring.py`

---

## Product (what's live)

| Asset | URL | Branch | Status |
|-------|-----|--------|--------|
| React app | [app.pvmath.com](https://app.pvmath.com) | `main` | ✅ Production |
| API | [api.pvmath.com](https://api.pvmath.com) | `main` | ✅ Production |
| Staging API | `pvmath-api-staging-production.up.railway.app` | `staging` | ✅ Pre-prod |
| Marketing | [pvmath.com](https://pvmath.com) | `main` | ✅ No RevenueIQ mention |
| Streamlit legacy | siteiq / topoiq subdomains | `main` | ⚠️ Retained |

### Unified workflow

Project Setup → SiteIQ → TerrainIQ → LayoutIQ → YieldIQ → Output (PDF + ZIP)

### Exports

Unified PVMath PDF · Project package ZIP (report + A1 layout + BOM + DXF + Terrain Data/)

### Deploy wiring

| Environment | Git | Railway | Env flags |
|-------------|-----|---------|-----------|
| Production | `main` | `exemplary-balance` | Redis, worker — **no** RevenueIQ |
| Staging | `staging` | `cozy-enjoyment` | Redis, worker, **`PVMATH_ENABLE_REVENUEIQ=1`** |

Cloudflare Preview: `VITE_API_URL` → staging API; optional `VITE_ENABLE_REVENUEIQ=true` when UI ships.

---

## Architecture (current)

```
app.pvmath.com ──► api.pvmath.com (FastAPI)
                        │
           ┌────────────┼────────────┐
           ▼            ▼            ▼
      Supabase     Redis/RQ      PVGIS/OSM/DEM
                   worker
```

| Layer | Key paths |
|-------|-----------|
| React | `frontend/src/pages/OutputPage.tsx` |
| API workflow | `api/routers/workflow.py` |
| Job queue | `api/jobs/`, `railway.worker.toml` |
| Scoring | `pvmath_workflow/score_config.py`, `scoring.py` |
| RevenueIQ | `revenueiq/` (staging) |
| Reports | `pvmath_reports/unified_report.py` |
| Roadmap | `PVMath/ARCHITECTURE_ROADMAP.md` |

**Readiness (after queue + R2 + monitoring):** ~72/100 @ 1K concurrent users (see roadmap).

---

## Pricing & billing

Unchanged — one SiteIQ screen = one credit; TerrainIQ/LayoutIQ/YieldIQ free same month. Stripe not live; manual Supabase activation.

---

## Immediate next steps

1. [ ] Push **`staging`** with RevenueIQ v0 + doc updates
2. [ ] Set `PVMATH_ENABLE_REVENUEIQ=1` on staging Railway API
3. [ ] **Project-package job queue** (architecture priority #1)
4. [ ] RevenueIQ React panel (staging preview only)
5. [ ] Stripe / Gewerbe (business — unchanged)

---

## Key files (quick index)

| Topic | Path |
|-------|------|
| **This file** | `PVMath/STATUS.md` |
| **Fresh chat bootstrap** | `docs/PVMath_Cursor_New_Session_Bootstrap.md` |
| **Architecture roadmap** | `PVMath/ARCHITECTURE_ROADMAP.md` |
| **RevenueIQ module** | `revenueiq/engine.py` |
| **Scoring** | `pvmath_workflow/score_config.py` |
| **Mount → Yield fix** | `pvmath_workflow/mount_utils.py` |
| **Job queue** | `api/jobs/` |

---

## How to resume in Cursor

Use the paste block in **`docs/PVMath_Cursor_New_Session_Bootstrap.md`** — it includes architecture + RevenueIQ context.

---

## Update rule

Edit this file first when something material ships. Update handoff table + latest commit hash.
