# PVMath AI Development Bible

Living architecture reference for Cursor sessions. Expand as the platform grows.

## Product vision

PVMath is a solar pre-construction intelligence platform. **Workflow 1 (Preliminary Study)** delivers realistic screening in minutes with minimal input. **Workflow 2 (Detailed Engineering)** will add LiDAR, survey points, detailed shading, and enterprise-grade simulation on the same foundation.

## Workflows

| Workflow | Status | Modules |
|----------|--------|---------|
| Preliminary Study | Active | Project Setup → SiteIQ → TerrainIQ → LayoutIQ → YieldIQ |
| Detailed Engineering | Future | + LiDAR, detailed layout solver, real shading, FinancialIQ, ReportIQ |

## UX principles

- Automation over manual input
- Essential fields first; expert options collapsed
- Sticky workflow navigation always visible
- Premium, minimal UI (Figma / Stripe / Notion quality)
- One clear purpose per screen

## Module responsibilities

- **Project Setup** — identity, location, boundary, smart defaults, readiness
- **SiteIQ** — solar, grid, flood, regulatory, capacity screening
- **TerrainIQ** — slope, elevation, terrain score (authoritative terrain)
- **LayoutIQ** — string-based layout, GCR/pitch sweep, capacity
- **YieldIQ** — PVGIS-based yield with layout-selected configuration

## Engineering assumptions (preliminary)

- Module: 550 Wp, 2.094 × 1.038 m, 28 modules/string, 500 mm string gap
- Terrain: EU-DEM (Europe) / SRTM (global)
- Irradiation: PVGIS
- Layout: equal pitch default; south-aligned tracker baseline
- Capacity: explicit geometry only (strings, gaps, roads optional)

## Data model

Projects stored in Supabase `user_projects.project_data` JSONB with `schema_version: 1`:

- `project_info`, `location`, `geometry`, `design_basis`, `assumptions`, `workflow`

Legacy flat payloads are normalized on read.

## API conventions

- `/api/v1/projects/*` — CRUD, validate, buildable-area
- `/api/v1/workflow/*` — screening, layout, terrain, yield, deliverables
- PATCH merges into existing `project_data` (no silent field loss)
- Auth: Supabase JWT Bearer

## Code conventions

- React: typed draft + reducer for Project Setup
- Python: business logic in `pvmath_*` modules, thin FastAPI routers
- No hardcoded values that should become user-configurable later
- Ground-mount only: Fixed Tilt, Single-Axis Tracker, Standard, Agri-PV

## Roadmap boundary

Do **not** build in preliminary phase: LiDAR upload, detailed shading, FinancialIQ, ReportIQ, Shapefile import, team-shared projects DB migration.
