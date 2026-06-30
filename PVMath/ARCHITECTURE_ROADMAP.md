# PVMath Architecture Roadmap

> **Last updated:** 1 Jul 2026  
> **Status:** Redis + workers live. Score v2 + economic viability on production. RevenueIQ v0 on staging.  
> **Resume here:** **Immediate** section — project-package queue first, then R2.

---

## Completed (platform foundation)

| Item | Staging | Production |
|------|---------|------------|
| FastAPI service | `pvmath-api-staging-production.up.railway.app` | `api.pvmath.com` |
| Redis job queue | Yes | Yes |
| Dedicated worker | Yes | Yes |
| Job kinds queued | `terrainiq.analyze`, `workflow.terrain_mesh`, `workflow.layout_sweep` | Same |
| PVMath score v2 + viability card | Yes | Yes (`f8c5b3f`) |
| YieldIQ mount / report fixes | Yes | Yes |
| **RevenueIQ v0 (API only)** | **Yes** (`PVMATH_ENABLE_REVENUEIQ=1`) | **No** |

**Key files:** `api/jobs/`, `pvmath_workflow/score_config.py`, `revenueiq/`, `railway.api.toml`, `railway.worker.toml`

---

## Immediate (next session — start here)

### 1. Project-package job queue ← **#1 architecture task**
Still synchronous — largest OOM/timeout risk at 1K users.

- `POST /workflow/project-package-job` + poll
- Handler in `api/jobs/handlers.py`
- Frontend: `workflowProjectPackageJob()` in `api.ts`
- **Branch:** `staging` first

### 2. RevenueIQ staging UI (parallel track)
- Panel on Output step — `VITE_ENABLE_REVENUEIQ=true` (Cloudflare Preview only)
- Wire `POST /revenueiq/analyze` with layout row + yield MWh
- **No website / marketing changes**

### 3. R2 for exports
PDF/ZIP/DXF off API RAM — presigned downloads.

### 4. Sentry + k6 baseline
Sentry on API + React; k6 100 VU smoke on staging.

---

## CTO priority roadmap (ordered)

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | Redis job queue | **Done** | Extend to **project-package**, GIS, report PDF |
| 2 | Dedicated workers | **Done** | Scale replicas when queue depth grows |
| 3 | **RevenueIQ v0** | **Staging API done** | UI + PDF next; not public |
| 4 | Cloudflare R2 artifacts | Pending | PDF/ZIP/DXF off RAM |
| 5 | Async API + JWT cache | Pending | Redis JWT ~60s |
| 6 | Monitoring | Pending | Sentry first |
| 7 | k6 load tests | Pending | 100→500 VU on staging |
| 8 | Rate limiting | Pending | Cloudflare WAF + FastAPI |
| 9 | Team / multi-tenancy | Later | Org RBAC |
| 10 | ECS/Kubernetes | Only if metrics justify | Railway OK to ~1K with queue + R2 |

---

## Readiness targets (1K concurrent users)

| Milestone | Readiness @ 1K |
|-----------|----------------|
| Today (queue for 3 job types) | ~55/100 |
| + project-package queue | ~62/100 |
| + R2 + Sentry | ~72/100 |
| + k6 validated + rate limits | ~78/100 |

---

## Railway reference

| Project | Branch | RevenueIQ |
|---------|--------|-----------|
| `cozy-enjoyment` | `staging` | `PVMATH_ENABLE_REVENUEIQ=1` on API |
| `exemplary-balance` | `main` | **Do not enable** |

**Health checks:**
```bash
curl -s https://api.pvmath.com/api/health/ready
curl -s https://pvmath-api-staging-production.up.railway.app/api/health/ready
```

---

## Session handoff (1 Jul 2026)

1. Read `PVMath/STATUS.md` + this file
2. Work on **`staging`** branch
3. Architecture: project-package queue
4. Product: RevenueIQ UI on staging preview
5. Promote `staging` → `main` only after verification

**Docs:** `docs/PVMath_Cursor_New_Session_Bootstrap.md`, `docs/PVMath_RevenueIQ_Staging.md`

---

## Shipped on main (1 Jul 2026)

SAT vs Fixed YieldIQ, score v2, economic viability card, LayoutIQ in report header — see `PVMath/STATUS.md`.
