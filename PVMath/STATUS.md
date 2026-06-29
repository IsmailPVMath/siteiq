# PVMath — Current Status

**Last updated:** 30 June 2026  
**Read this first** when starting a new Cursor session. Then `CLAUDE.md` for deeper technical history (some sections are Streamlit-era — **this file takes precedence** for architecture, pricing, and what’s live).

---

## One-line summary

**Unified PVMath-Solar Site Intelligence Platform** at **app.pvmath.com** (React + FastAPI): one guided workflow from coordinates/boundary through screening, terrain, layout, and yield. **Project ZIP** = unified PVMath PDF + **A1 layout sheet** + BOM CSV + layout DXF + lean **Terrain Data/** folder. **Per-project analysis billing** (10 / 50 / 250 / unlimited per month). **Stripe not live** — manual Supabase activation. Streamlit (`siteiq` / `terrainiq` subdomains) retained in repo; **primary product is the React app**.

---

## Session handoff (30 Jun 2026)

**`main` is clean and pushed.** Latest: `5fcc202` — *Unified report: SiteIQ screening cards; stale capacity estimate removed.* **`staging` synced with `main`.*

### Shipped this session (production `main`)

| Area | What |
|------|------|
| **Unified report (SiteIQ)** | Removed stale **Est. DC capacity** from Project Summary; removed **OVERALL VERDICT** + **KEY DRIVERS** from page 1; added four-tile screening snapshot (Solar, Flood, Grid proximity from OSM, Regulatory/tariff) matching the React SiteIQ step; GHI chart + next steps unchanged; final **PVMath score** at report end unchanged |
| **Project Setup** | Pin + area → square envelope (`squareBoundaryFromPin`); explicit **Create area** button (no live typing flicker); area bar below map; reverse-geocode location (no manual country/city fields); **New project** dropdown resets draft; save draft at bottom |
| **TerrainIQ** | Multi-cluster DEM for disconnected parcels far apart (`pvmath_topo_engine.py` cluster + composite slope map); standalone Terrain PDF/CAD ZIP buttons **removed** from UI |
| **LayoutIQ** | Exclusions + constraint layers on map preview and A1 PDF (red hatched keep-outs, rivers/transmission lines); hole-preserving `restriction_geojson`; aligned row-packing fills pockets separated by exclusions; `prune_isolated_blocks` threaded through package API; screen vs ZIP layout **param parity** (was mismatching tracker counts) |
| **A1 layout sheet** | Upgraded from A3 — large top view, north arrow, scale bar, sidebar BOM/metrics; PVMath rounded logo lockup; legend docked outside plot |
| **BOM** | Inverters sized by power at DC:AC ~1.2 (was ~0.6 / 2× too many); posts/rails mount-aware; BOM from **merged** multi-parcel layout |
| **Project package ZIP** | `Terrain Data/`: `{base}_reference.json`, `{base}_points.csv` (UTM E/N/Z), `{base}_contours_georef.dxf` only — **no** slope PDF (in PVMath report), no auto LandXML/local DXF |
| **TerrainIQ on demand** | Sidebar buttons: **LandXML** + **DXF (local origin)** via `POST /terrainiq/export/landxml` and `/export/contours-local` |
| **Marketing** | `services/index.html` (standalone Services page); website unified-platform copy, per-project pricing, data sources (EEA-10, FABDEM, 3DEP) |
| **Docs** | `docs/PVMath_Cursor_New_Session_Bootstrap.md` — paste block for fresh Cursor chats |

### Verify tomorrow (if needed)

- [ ] **app.pvmath.com** — full workflow on a ~100 ha DE site: pin+area envelope → SiteIQ → TerrainIQ (multi-parcel if applicable) → LayoutIQ with exclusions visible → project package ZIP
- [ ] Confirm A1 layout tracker count **matches** on-screen layout; BOM inverters ~DC/1.2/100 kW (not 2× inflated)
- [ ] Unified PDF page 1: four screening cards (Solar/Flood/Grid/Regulatory), **no** Est. DC capacity row, **no** verdict/key drivers on SiteIQ section
- [ ] Terrain Data folder has 3 files only; LandXML/local DXF buttons work on demand
- [x] **Staging sync** — `main` merged into `staging` (30 Jun 2026)

### Known limitations / next engineering

| Topic | Notes |
|-------|--------|
| **Terrain package cost** | Each package download still **re-runs** `run_topo_analysis` (DEM fetch). Lean bundle is faster but not free. **Cache grid after first TerrainIQ run** = biggest win. |
| **On-demand CAD** | LandXML / local DXF each re-run full analysis today (~10–60s). Same cache would make them instant. |
| **Prune islands** | Pockets within ~1 row-pitch of main array count as “connected” by design — only truly separated islands drop. |
| **Capacity screening** | `pvmath_capacity.py`: base density × GCR/0.30; band GCR 0.30–0.42. Screening no longer shows MWp estimate in unified PDF — capacity is **LayoutIQ only**. |

### Likely next product tasks

- Stripe / Gewerbe (unchanged — see Immediate next steps)
- Cache TerrainIQ analysis artifacts for package + on-demand exports
- Optional: background job for project package on large sites
- EPC review feedback loop from senior engineer red-flag session (BOM credibility, screening disclaimers)

---

## Business & legal

| Item | Status |
|------|--------|
| Legal form | **Einzelunternehmen** (Mohammed Ismail Pasha, trading as PVMath) — registering |
| Steuerberater | Approved sole prop + personal bank account for payments |
| UG (haftungsbeschränkt) | **Deferred** |
| Gewerbe Regensburg | **TODO** |
| Steuernummer / USt-IdNr | **TODO** |
| Ideematec Nebentätigkeit | Confirm / disclose if contract requires |
| IHK | Automatic after Gewerbe |

**Public legal pages:** `impressum.html`, `privacy.html`, `terms.html` — per-project usage, app.pvmath.com.  
**Services page:** `services/index.html` — DACH market entry, project development advisory, BD consulting.

---

## Product (what’s live)

| Asset | URL | Host | Status |
|-------|-----|------|--------|
| **PVMath platform (primary)** | [app.pvmath.com](https://app.pvmath.com) | Cloudflare Pages (`frontend/`) | ✅ Production |
| **API** | [api.pvmath.com](https://api.pvmath.com) | Railway (`api/`, FastAPI) | ✅ Production |
| **Marketing** | [pvmath.com](https://pvmath.com) | GitHub Pages (`index.html`, `services/`) | ✅ Production |
| Streamlit (legacy) | siteiq.pvmath.com, topoiq.pvmath.com | Railway (`app.py`) | ⚠️ Retained — not primary |

### Unified workflow (React)

1. **Project Setup** — pin/coords/search, draw boundary, upload KML, or **pin + ha → square envelope**
2. **SiteIQ** — PVGIS, OSM constraints, flood, regulatory, capacity screening (mount-agnostic)
3. **TerrainIQ** — region-routed DEM, slope map, 3D preview; CAD on demand
4. **LayoutIQ** — **mount type here** (FT / SAT); GCR sweep, exclusions on map, prune islands, BOM preview
5. **YieldIQ** — auto-runs on step entry; PVGIS yield table

### Exports

| Deliverable | Where |
|-------------|--------|
| **Unified PVMath PDF** | Output → download (`pvmath_reports/unified_report.py`) |
| **Project package ZIP** | Output → download: `{Project}_PVMath_Report.pdf`, `{Project}_Layout_A1.pdf`, `{Project}_BOM.csv`, layout DXF, **`Terrain Data/`** (3 files if TerrainIQ was run) |
| **LandXML** | TerrainIQ sidebar — on demand |
| **Contour DXF (local origin)** | TerrainIQ sidebar — on demand |
| **Layout DXF** | Inside package + LayoutIQ export |

No GLB export. No standalone TerrainIQ PDF/ZIP buttons in UI (terrain in package + PVMath report).

### Data sources

| Data | Source |
|------|--------|
| Solar / yield | PVGIS (JRC) |
| Terrain DEM | Region-routed: Copernicus EEA-10 (EU), USGS 3DEP (USA), FABDEM (global), GLO-30 fallback — `pvmath_terrain_sources.py` |
| Geocoding | Nominatim / OSM |
| Constraints | OSM layers + setbacks — `pvmath_workflow/gis_analysis.py` |

### Deploy wiring

| Environment | Git branch | Host |
|-------------|------------|------|
| Production API | `main` | Railway `exemplary-balance` |
| Staging API | `staging` | Railway `cozy-enjoyment` |
| React app | `main` | Cloudflare Pages — `cd frontend && npm ci && npm run build` → `frontend/dist`, `VITE_API_URL=https://api.pvmath.com` |
| Marketing | `main` | GitHub Pages |

**Latest production commit:** `5fcc202`

Recent stack: `5fcc202` SiteIQ screening cards in unified PDF · `668d999` lean Terrain Data + on-demand CAD · `501c8a2` LayoutIQ/report/BOM fixes · `7cdf3d8` A1 sheet + GIS overlays · `2dc9443` multi-cluster terrain.

---

## Pricing & billing

**One project analysis** = one SiteIQ screening run. TerrainIQ, LayoutIQ, YieldIQ on same project same month = **no extra credits**.

| Plan | Price | Limit |
|------|-------|-------|
| Free | €0 | **10** analyses / month |
| Professional | €149/mo | **50** / month |
| Developer | €499/mo | **250** / month, 5 team seats |
| Enterprise | Custom | Unlimited |

| Billing piece | Status |
|---------------|--------|
| Counter | `usage_tracking.app = 'platform'` |
| Charged on | SiteIQ screen only |
| Stripe | **Not live** — manual Supabase activation (`docs/PVMath_Manual_Billing_Runbook.md`) |
| Team invites | ✅ `pvmath_team.py` |

---

## App UX (React — current)

- **Project Setup** — assumed square boundary from pin+area unlocks full workflow without drawing
- **Mount type** — LayoutIQ only; SiteIQ/TerrainIQ screening uses mount only at report time
- **GIS** — buildable mask clips TerrainIQ; exclusions render on LayoutIQ map + A1 PDF
- **LayoutIQ** — `prune_isolated_blocks`, `row_alignment`, `allow_partial_strings`, `ignore_soft_constraints` all sent to API + package
- **YieldIQ** — auto-run on step; mount filter in results panel
- **3D terrain** — viewer only (no export)
- **Auto-save** — debounced on workflow step change

---

## Architecture

```
pvmath.com + services/     app.pvmath.com (React/Vite)
        │                              │
        └──────────────┬───────────────┘
                       ▼
              api.pvmath.com (FastAPI)
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
    Supabase      PVGIS/OSM     Region DEM
```

| Layer | Key paths |
|-------|-----------|
| React UI | `frontend/src/pages/OutputPage.tsx`, `ProjectSetupPage.tsx`, `components/LayoutPreviewMap.tsx` |
| API | `api/routers/workflow.py`, `terrainiq.py` |
| Reports | `pvmath_reports/unified_report.py`, `siteiq_section.py`, `pvmath_workflow/project_report.py` |
| Layout | `layoutiq/engine.py`, `drawing.py`, `bom.py` |
| Terrain bundle | `pvmath_workflow/terrain_bundle.py` |
| Capacity | `pvmath_capacity.py` (single source of truth for screening MWp bands) |
| Topo engine | `pvmath_topo_engine.py` (multi-cluster parcels) |

---

## Immediate next steps (priority order)

1. [ ] **Stripe** — Payment Links (Pro €149, Dev €499)
2. [ ] **Gewerbe** + Steuernummer / USt-IdNr
3. [ ] **Cache TerrainIQ** grid/exports after first analyze (package + on-demand CAD)
4. [x] Sync **`staging`** with `main` (30 Jun 2026)
5. [ ] Retire Streamlit production when comfortable
6. [ ] Update **this file** after each milestone

---

## Key files (quick index)

| Topic | Path |
|-------|------|
| **This file** | `PVMath/STATUS.md` |
| **Fresh chat bootstrap** | `docs/PVMath_Cursor_New_Session_Bootstrap.md` |
| Project package ZIP | `pvmath_workflow/project_report.py` → `build_project_package_zip` |
| Terrain package / on-demand | `pvmath_workflow/terrain_bundle.py`, `api/routers/terrainiq.py` |
| A1 layout drawing | `layoutiq/drawing.py`, `pvmath_workflow/project_report.py` → `build_layout_sheet_pdf` |
| SiteIQ PDF key drivers | `pvmath_reports/siteiq_section.py`, `siteiq_suitability.py` |
| Capacity bands | `pvmath_capacity.py` |
| Layout engine | `layoutiq/engine.py` |
| Founder Handbook | `PVMath/README.md` |
| AI long memory | `CLAUDE.md` |

---

## How to resume in Cursor

Paste as first message:

```
Continue PVMath. Read PVMath/STATUS.md first (session handoff at top).
git log -5 on main. Next task: [describe what you want].
```

Or use `docs/PVMath_Cursor_New_Session_Bootstrap.md` for a fuller bootstrap block.

---

## Update rule

When something material changes, **edit this file first** — one-line summary, handoff table, latest commit. Takes 2 minutes; saves re-explaining in every new session.
