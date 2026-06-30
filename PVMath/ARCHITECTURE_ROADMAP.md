# PVMath Architecture Roadmap

> **Last updated:** 30 Jun 2026  
> **Status:** Platform foundation (Redis + workers) live on staging and production.  
> **Resume here:** Next engineering session — continue from **Immediate** section below.

---

## Completed (platform foundation)

| Item | Staging | Production |
|------|---------|------------|
| FastAPI service | `pvmath-api-staging-production.up.railway.app` | `api.pvmath.com` |
| Redis job queue | Yes | Yes |
| Dedicated worker | Yes | Yes (`PVMath-Worker-1`, `railway.worker.toml` or `python -m api.jobs.worker`) |
| Job kinds queued | `terrainiq.analyze`, `workflow.terrain_mesh`, `workflow.layout_sweep` | Same |
| React preview → staging API | Cloudflare `*.pages.dev` + CORS fix | — |
| Merge `staging` → `main` | Done | Done |

**Key files:**
- `api/jobs/` — memory + Redis/RQ backends
- `railway.api.toml` — API
- `railway.worker.toml` — worker
- `frontend/src/lib/apiBase.ts` — preview API URL fallback

---

## Immediate (next session — start here)

### 1. Production smoke test
On **app.pvmath.com**, run one full project end-to-end:
- SiteIQ → TerrainIQ → LayoutIQ sweep → PDF or ZIP download

Confirms prod API + worker + Redis under real use.

### 2. Queue **project-package** (highest remaining engineering risk)
Still synchronous on API — largest OOM/timeout risk at scale.

**Implementation pattern** (same as layout-sweep):
- `POST /workflow/project-package-job` + status poll
- Handler in `api/jobs/handlers.py`
- Frontend: `workflowProjectPackageJob()` in `api.ts`

### 3. Optional cleanup
- Delete Streamlit staging in `cozy-enjoyment` if still present
- Confirm prod worker uses `/railway.worker.toml` or start command `python -m api.jobs.worker`

---

## CTO priority roadmap (ordered)

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | Redis job queue | **Done** | Extend to project-package, GIS, report PDF |
| 2 | Dedicated workers | **Done** | Scale replicas when queue depth grows |
| 3 | Cloudflare R2 artifacts | Pending | PDF/ZIP/DXF off RAM; presigned downloads |
| 4 | Async API + JWT cache | Pending | httpx async; Redis JWT cache ~60s |
| 5 | Monitoring | Pending | Sentry + OTEL + Grafana (start with Sentry) |
| 6 | k6 load tests | Pending | Staging first; 100→500 VU scenarios |
| 7 | Rate limiting | Pending | Cloudflare WAF + FastAPI middleware |
| 8 | Team / multi-tenancy | Later | Org RBAC, audit logs |
| 9 | AI infrastructure | Later | — |
| 10 | ECS/Kubernetes | Only if metrics justify | Railway OK for hundreds of concurrent users |

---

## Recommended build order (engineering)

1. **Project-package job queue** ← next code task  
2. **R2 for exports** (ZIP, PDF, DXF, terrain bundle)  
3. **Sentry** (API + React)  
4. **JWT cache** (Redis)  
5. **Async Supabase** (projects, auth deps)  
6. **k6 smoke** on staging  
7. **Rate limits** by plan tier  

---

## “Platform foundation complete” checklist

- [x] Staging API + worker + Redis  
- [x] Production API + worker + Redis  
- [x] React preview → staging  
- [ ] Project-package queued  
- [ ] R2 for large downloads  
- [ ] Basic monitoring (Sentry minimum)  
- [ ] Load test baseline (k6 100 VU)  

---

## Readiness targets (from architecture review)

| Concurrent users | Before queue | After foundation | After R2 + monitoring |
|------------------|--------------|------------------|------------------------|
| 500 | ~22/100 | ~65/100 | ~78/100 |
| 1,000 | ~12/100 | ~55/100 | ~72/100 |
| 5,000 | ~8/100 | ~40/100 | ~85/100 (needs worker autoscale) |

---

## Railway reference

| Project | Branch | API | Worker config |
|---------|--------|-----|---------------|
| `cozy-enjoyment` | `staging` | `railway.api.toml` | `railway.worker.toml` |
| `exemplary-balance` | `main` | `railway.api.toml` | `railway.worker.toml` |

**Worker env (both):** `REDIS_URL`, `PVMATH_JOB_BACKEND=redis`, copy Supabase/compute vars from API.

**Health checks:**
```bash
curl -s https://api.pvmath.com/api/health/ready
curl -s https://pvmath-api-staging-production.up.railway.app/api/health/ready
```

---

## Cloudflare reference

| Environment | `VITE_API_URL` |
|-------------|----------------|
| Production | `https://api.pvmath.com` |
| Preview | `https://pvmath-api-staging-production.up.railway.app` |

Preview builds on `*.pages.dev` auto-use staging API via `frontend/src/lib/apiBase.ts` if `VITE_API_URL` missing at build time.

---

## Session handoff

When resuming architecture work:
1. Read this file + `PVMath/STATUS.md`
2. Run production smoke test if not done
3. Implement project-package queue on `staging` first
4. Promote to `main` after verification

---

## Urgent fixes (1 Jul 2026) — SAT vs Fixed YieldIQ / score / report

| # | Issue | Root cause | Fix |
|---|--------|------------|-----|
| 1 | YieldIQ/PDF showed Fixed after SAT 1P selected | `Compare FT & SAT` left `mountFilter=all` and report `mount_type=Compare FT & SAT` | Derive mount from **selected layout row** (`yieldMountFilter`, `effectiveMountType`, `pvmath_workflow/mount_utils.py`) |
| 2 | Score stuck ~58/100 | Terrain cap `min(weighted, terrain+15)`; yield not in live score API | Pass `yield_spec_y` to `/workflow/score` after YieldIQ runs |
| 3 | Report header missing LayoutIQ | Banner text outdated | `SiteIQ · TerrainIQ · LayoutIQ · YieldIQ` |
| 4 | Cross-module ref looked “stale” | Always shown; compares SiteIQ screening vs YieldIQ (informational) | Hidden when a single mount is selected (not compare mode) |
| 5 | Aurora/DNV/PVsyst line in YIQ UI | Copy in `YieldResultsPanel` + PDF | Removed from on-screen screening summary |
| 6 | Missing tracker row(s) | Often E-W block roads, NS block gaps, restrictions, or `prune_isolated_blocks` | **Investigate per project** — check road preset, `cols_per_block`, `ew_gap_m`, exclusions |

**Re-test Ismaning 7 ha:** Select SAT 1P row → YieldIQ step → Re-run YieldIQ → regenerate PDF.
