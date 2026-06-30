# Cursor — Fresh Session Bootstrap Prompt

**Updated:** 1 July 2026  
Use this at the start of every new Cursor chat. It re-orients from repo state — no stale bug lists from old conversations.

---

## Paste this into the new Cursor chat

```
Fresh PVMath session — re-orient entirely from the repo:

1. Read PVMath/STATUS.md (session handoff at top — authoritative for what's live vs in progress).
2. Read PVMath/ARCHITECTURE_ROADMAP.md (CTO priority list — start at "Immediate").
3. Read CLAUDE.md for deployment wiring and git workflow only (some sections are Streamlit-era).
4. Run: git branch --show-current && git log --oneline -10 && git status

Give me a short summary:
- What's on production main vs staging
- What's mid-flight (uncommitted)
- Top 3 engineering priorities from STATUS + ARCHITECTURE_ROADMAP

Standing rules:
- Day-to-day fixes on staging first; main = production only when I say promote.
- RevenueIQ is STAGING ONLY — never add to pvmath.com, index.html, or production Railway until I say so.
- RevenueIQ API requires PVMATH_ENABLE_REVENUEIQ=1 (set on cozy-enjoyment, not exemplary-balance).

Then wait for my task — don't change code until I confirm.

Current focus areas (pick up where we left off):
A) Architecture expansion for ~1K concurrent users (project-package queue → R2 → Sentry → k6)
B) RevenueIQ v0 → UI on staging preview → PDF section → optional score factor
C) Production smoke test if not done since f8c5b3f
```

---

## Context cheat sheet (Jul 2026)

### Production (`main`, latest `f8c5b3f`)
- React app app.pvmath.com + api.pvmath.com
- Redis/RQ worker for terrain analyze, terrain mesh, layout sweep
- PVMath score v2: 22/22/18/15/15/8 weights, regional yield, economic viability card
- YieldIQ mount fix: selected LayoutIQ row drives yield filter + PDF (SAT vs Fixed)

### Staging (`staging`)
- Same as main + **RevenueIQ v0** (backend model + gated API)
- Enable: Railway API env `PVMATH_ENABLE_REVENUEIQ=1`
- Endpoint: `POST /api/v1/revenueiq/analyze` (404 on prod without flag)
- **Not on website** — no marketing copy, no public module list

### RevenueIQ inputs/outputs
- **In:** country, land_use, mount_type, dc_kwp (LayoutIQ), annual_mwh (YieldIQ), terrain_grade
- **Out:** revenue €/yr band, CAPEX € band, payback yrs, LCOE €/MWh — screening only
- **Files:** `revenueiq/engine.py`, `revenueiq/tariffs.py`, `revenueiq/capex.py`

### Architecture next (1K users)
1. Queue project-package ZIP (`api/jobs/handlers.py` pattern from layout-sweep)
2. Cloudflare R2 for PDF/ZIP artifacts
3. Sentry + k6 baseline on staging

### Git workflow reminder
```bash
cd ~/Desktop/solarscout
git checkout staging && git pull origin staging
# … work …
git add -A && git commit -m "…"
git push origin staging
# Test Cloudflare preview → promote: merge staging → main when verified
```

---

## Notes

- Cursor slowness = long chat history. New chat + this bootstrap = clean context in ~4 tool calls.
- For one-off tasks, use a separate brief (see `docs/PVMath_Cursor_Brief_*.md` pattern).
- Update this file when handoff priorities change.
