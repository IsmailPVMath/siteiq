# Cursor Brief — Harden Save Project against transient "Network error"

**Requested by:** Mohammed Ismail Pasha, 2026-06-27
**Symptom:** Save Project (and Proceed to Next Stage) occasionally shows "Network error — could not reach the PVMath server. Check your connection and try again," even though the save usually succeeds on retry.

## Root cause (from code)

This message only fires when the browser's `fetch()` promise itself rejects — i.e. no HTTP response came back at all (`frontend/src/lib/api.ts`, `apiFetch()` catch block, and `downloadBlob()`'s catch block). It is never shown for a clean HTTP error (4xx/5xx), only for a dropped/failed connection. Most likely trigger: a Railway redeploy/cold-start in progress at the moment of the request (you'd just shipped the projects-list fix), or a brief network blip — not a logic bug.

Two real inefficiencies make this more likely to happen, and worth fixing regardless of root cause:

1. **Every save recomputes Shapely buildable-area, even for metadata-only saves.** `partial_update_project()` (`api/routers/projects.py:153-185`) always calls `_buildable_area()` on the *merged* site boundary + restrictions — even when the patch from the client only contains `{name, workflow}` (which is what `handleSaveProject()` in `OutputPage.tsx:565-592` sends on every save after the first). This adds an unnecessary GET-merge-Shapely-PATCH round trip to what should be a tiny write, and is wasted load on every single save during a session.
2. **No retry for raw fetch failures.** `apiFetch()` already does a token-refresh retry when it gets a 401, but a raw `fetch()` rejection (the actual error you saw) goes straight to the generic message with zero retry — even though this class of failure is often transient (a redeploy finishing, a brief blip).

## Fix

### 1. Skip buildable-area recompute when geometry isn't part of the patch
`api/routers/projects.py`, `partial_update_project()` (~line 163):

```python
existing = get_project(project_id, user)
current = normalize_legacy_project_data(existing.project_data or {})
patch = {k: v for k, v in body.model_dump(exclude_none=True).items()}
merged = merge_project_data(current, patch)

geometry_touched = "site_boundary_geojson" in patch or "restriction_polygons_geojson" in patch
if geometry_touched:
    buildable_geo, buildable_ha = _buildable_area(
        merged.get("site_boundary_geojson") or {},
        merged.get("restriction_polygons_geojson"),
    )
    merged["buildable_area_geojson"] = buildable_geo or merged.get("buildable_area_geojson")
    merged.setdefault("workflow", {})
    merged["workflow"]["buildable_area_ha"] = buildable_ha
```
i.e. only run `_buildable_area()` when the incoming patch actually changes geometry. Metadata-only saves (the common case from `OutputPage.handleSaveProject()`) become a plain merge + PATCH — faster and lighter on every keystroke-triggered save.

Leave `update_project()` (the full PUT) and `create_project()` unchanged — those legitimately need a fresh computation every time.

### 2. Add one transparent retry on raw fetch failure
`frontend/src/lib/api.ts`, inside `apiFetch()`'s catch block (~line 60-67), wrap the raw `fetch()` call so a network-level failure (caught `TypeError`) gets one retry after a short delay before throwing:

```ts
async function fetchWithRetry(url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (err) {
    await new Promise((r) => setTimeout(r, 800));
    try {
      return await fetch(url, init);
    } catch {
      throw err;
    }
  }
}
```
Use `fetchWithRetry` in place of the direct `fetch()` call inside `apiFetch()` (and `downloadBlob()`). This absorbs exactly the transient redeploy/blip case without changing behavior for a genuinely unreachable server (you'd still get the same message after the retry fails too).

## Out of scope — don't touch unless separately asked
Token-refresh retry logic (already correct), `update_project`/`create_project` buildable-area logic, any UI copy changes to the error message itself.

## Verify after deploying
1. Trigger several Save Project clicks in a row on staging — confirm no behavior change for normal saves.
2. Temporarily stop the staging API (or redeploy mid-save) to confirm the retry now absorbs a one-shot blip instead of immediately showing the network error.
3. Confirm a metadata-only save (rename project) on an existing project still returns the correct `buildable_area_ha` unchanged from before.
