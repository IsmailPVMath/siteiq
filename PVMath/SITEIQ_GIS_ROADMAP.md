# SiteIQ Intelligent GIS — Roadmap

**Goal:** Make PVMath SiteIQ better than generic screening tools by automatically performing intelligent GIS analysis — no manual constraint drawing unless the user overrides.

**Last updated:** June 2026

---

## Vision

When a user defines a site boundary, PVMath should **automatically**:

1. Pull base maps (OSM, satellite, DEM via TopoIQ)
2. Detect mapped constraints (roads, rail, buildings, water, forest, power lines)
3. Apply configurable engineering setbacks
4. Generate **buildable polygons**
5. Display an interactive constraint map with area statistics

This feeds LayoutIQ (realistic capacity), YieldIQ (shading context), and the PVMath report/score.

---

## Phase 1 — Foundation (this release)

| Item | Status |
|------|--------|
| OSM Overpass constraint query inside site polygon | Done |
| Categories: roads, railways, buildings, rivers, lakes, canals, forests, water, transmission | Done |
| Configurable setbacks (`DEFAULT_SETBACKS_M` in `gis_constraints.py`) | Done |
| Buildable = site − setbacks − buffered constraints − manual restrictions | Done |
| API `POST /api/v1/workflow/gis-analysis` | Done |
| SiteIQ results: stats table + `ConstraintAnalysisMap` (satellite + OSM, layer toggles) | Done |

**Key files**

- `pvmath_workflow/osm_client.py` — Overpass client
- `pvmath_workflow/gis_constraints.py` — feature detection + layer styles
- `pvmath_workflow/buildable_engine.py` — setback + difference logic
- `pvmath_workflow/gis_analysis.py` — orchestrator
- `frontend/src/components/ConstraintAnalysisMap.tsx` — interactive map

**Default setbacks (m)** — override per request via `setbacks_m`:

| Constraint | Setback |
|------------|---------|
| Site boundary | 5 |
| Roads | 5 |
| Railways | 30 |
| Buildings | 10 |
| Rivers / lakes / water | 50 |
| Canals | 30 |
| Forests | 20 |
| Transmission lines | 100 |

---

## Phase 2 — Terrain + slope as constraints

| Item | Status |
|------|--------|
| Merge TopoIQ slope mask into GIS buildable (not tracker-only) | Planned |
| Elevation / aspect overlays on constraint map | Planned |
| DEM hillshade base layer | Planned |
| Distance labels from boundary to nearest constraint | Planned |

Uses existing `pvmath_workflow/slope_restrictions.py` + `pvmath_topo_engine.py`.

---

## Phase 3 — Richer data sources

| Item | Status |
|------|--------|
| CORINE / land-cover classes (EU) | Planned |
| Protected areas / Natura 2000 | Planned |
| Administrative boundaries (auto country/region confirm) | Planned |
| Real flood layers (HAND / national datasets) | Planned |
| LiDAR / survey upload (Detailed Engineering workflow) | Planned |

---

## Phase 4 — Score + report integration

| Item | Status |
|------|--------|
| `land` score from buildable % (not hardcoded 72/80) | Done |
| Constraint summary in PVMath PDF report | Planned |
| A3 layout sheet with constraint + buildable layers | Planned |
| Pass GIS exclusions to LayoutIQ as default build envelope | Done |

---

## Phase 5 — UX polish

| Item | Status |
|------|--------|
| Setback editor in Advanced options (per category) | Planned |
| Re-run GIS on boundary change in Project Setup | Planned |
| Project Setup map: satellite toggle + constraint preview | Planned |
| Constraint click → name + setback distance popup | Planned |

---

## Architecture notes

- **Do not copy Glint Solar** — PVMath differentiators: global DEM routing (EU/US/world), integrated LayoutIQ string geometry, TopoIQ authoritative terrain, unified PVMath score with terrain cap.
- **OSM disclaimer** always shown — coverage gaps are common; setbacks are engineering assumptions.
- **Overpass timeout** default 90s; endpoint timeout 120s (`PVMATH_GIS_TIMEOUT`).
- Buildable computation reuses Shapely patterns from `api/routers/projects.py`.
