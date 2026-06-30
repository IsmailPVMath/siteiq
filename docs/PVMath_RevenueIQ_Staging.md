# RevenueIQ — Staging Module Spec

**Status:** v0 backend on `staging` (1 Jul 2026)  
**Visibility:** Private — not on pvmath.com, not in production until promoted.

---

## Scope (v0 — screening)

Headline economics from existing workflow outputs. **Not** a bankable financial model.

| Metric | Method |
|--------|--------|
| Annual revenue | `annual_mwh × tariff_band` (country + land use) |
| CAPEX | `dc_kwp × €/Wp band` (mount + terrain uplift) |
| OPEX | 1.5–2.5% of CAPEX / year |
| Payback | CAPEX / (revenue − OPEX), best/worst band |
| LCOE | (CAPEX + OPEX×25) / (MWh×25), no discount rate |

---

## API

```
POST /api/v1/revenueiq/analyze
Authorization: Bearer <token>
```

**Requires:** `PVMATH_ENABLE_REVENUEIQ=1` on API service (404 otherwise).

**Request body:**
```json
{
  "country": "Germany",
  "land_use": "Standard",
  "mount_type": "Single-Axis Tracker",
  "dc_kwp": 3942.4,
  "annual_mwh": 4522,
  "terrain_grade": "challenging"
}
```

---

## v1 roadmap (staging → production)

| Step | Effort | Notes |
|------|--------|-------|
| v0 model + API | Done | This commit |
| Staging UI panel | ~2 days | `VITE_ENABLE_REVENUEIQ=true` on preview only |
| PDF section | ~1 day | After UI validated |
| Score factor (~10%) | ~1 day | Optional revenue subscore in `score_config.py` |
| DE EEG refinement | ~3 days | Auction year bands, direct marketing |
| US ITC / PPA stub | ~2 days | Extend `tariffs.py` |
| Promote to main | — | Only when user approves + website copy ready |

**Total to useful staging demo:** ~1 week part-time after v0.

---

## Files

| File | Role |
|------|------|
| `revenueiq/tariffs.py` | Country revenue bands |
| `revenueiq/capex.py` | €/Wp + terrain uplift |
| `revenueiq/engine.py` | Orchestration |
| `api/routers/revenueiq.py` | FastAPI router |
| `api/schemas/revenueiq.py` | Pydantic models |
| `tests/test_revenueiq.py` | Unit tests |

---

## Railway staging setup

On **cozy-enjoyment** API service → Variables:
```
PVMATH_ENABLE_REVENUEIQ=1
```

Do **not** set on **exemplary-balance** (production).
