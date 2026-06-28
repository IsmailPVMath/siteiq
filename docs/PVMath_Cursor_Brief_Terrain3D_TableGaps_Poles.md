# Cursor Brief — Real per-table gaps + clearer poles in TerrainIQ 3D view

**Requested by:** Mohammed Ismail Pasha, 2026-06-27
**Goal:** Make the 3D layout preview show the actual 0.5 m table gaps that already exist in the 2D layout, and make the support poles visually legible (they're geometrically correct today, just invisible under the tables from most camera angles).

**Files touched:** `layoutiq/engine.py`, `pvmath_workflow/layout_detail.py`, `frontend/src/lib/terrain3dScene.ts`, `frontend/src/components/Terrain3DView.tsx`

---

## Why this is happening (confirmed in code)

The backend already computes correct per-table geometry. `layoutiq/engine.py`'s row-sweep loop produces two parallel outputs per row segment: `rows_polys` (one merged polygon spanning the whole row, used for "pv_row" features) and `string_polys` (one polygon per individual table/string, already separated by `inter_string_gap_m` = 0.5 m, used for "pv_module" features — `pvmath_workflow/layout_detail.py:208-222`). The 2D layout view renders the gapped `pv_module` polygons, which is exactly why your 2D screenshot shows the gaps correctly.

The 3D code only reads `pv_row`. `parseLayoutRows()` in `terrain3dScene.ts:154-180` explicitly filters for `properties?.kind === "pv_row"` and has a comment: *"Do not fall back to per-string polygons — clipped fragments collapse the 3D view."* Someone tried using `pv_module` before, hit degenerate/sliver fragments on clipped row edges, and worked around it by merging everything into one continuous table box per row instead of fixing the underlying issue. That's why every row renders as a single uninterrupted blue ribbon today.

Poles are already anchored correctly to terrain (`toThreePosition(lx, north, sampler(lx, north), postH/2, ...)`, `terrain3dScene.ts:388-398`) — they're just thin (6–9 cm radius) and sit directly under a full-width opaque table top, so from a moderately top-down camera they're hidden. Not a correctness bug, a legibility one.

## Fix — Part 1: tag each table polygon with its parent row (backend)

`pv_module` features currently carry no link back to which row they belong to (`layout_detail.py:208-222` — only `string_index`, `modules_per_string`, `n_modules`). Without that link, the frontend can't position posts/torque-tube under the right group of tables.

In `layoutiq/engine.py`, inside `row_sweep_layout` (or whatever the row-sweep function is named at this call site — see the `for seg_min, seg_max in segments:` loop you already have), track which row-local index each string belongs to:

```python
# right after rows_polys.append(row_orig) / rows_polys.extend(...)
row_local_idx = len(rows_polys) - 1   # index of the row just added for this segment

# ... existing string-building loop ...
for srect in _string_rects_in_segment(...):
    ...
    string_polys.append(s_orig)
    string_row_local_idx.append(row_local_idx)   # new parallel list, same length as string_polys
```

Initialize `string_row_local_idx: list[int] = []` alongside `string_polys = []` near the top of the function, and include it in the returned dict (alongside `"string_polys"`).

Note: on concave parcels a single segment can clip into a `MultiPolygon`, adding more than one entry to `rows_polys` from one segment — in that edge case all of that segment's strings get tagged with the same (first) row-local index. That's an acceptable approximation; flag it in a code comment, don't try to solve it now.

In `pvmath_workflow/layout_detail.py`, capture the row-index offset before processing each layout's rows, and use it when building `pv_module` features (~line 196-222):

```python
for layout in layouts:
    row_index_base = row_index  # capture BEFORE this layout's row loop increments it
    ...
    for s_idx, spoly in enumerate(layout.get("string_polys") or []):
        string_index += 1
        local_row_idx = (layout.get("string_row_local_idx") or [])[s_idx] if s_idx < len(layout.get("string_row_local_idx") or []) else 0
        features.append(
            _polygon_feature(spoly, ref_lat, ref_lon, {
                "kind": "pv_module",
                "string_index": string_index,
                "modules_per_string": layout["modules_per_string"],
                "n_modules": layout["modules_per_string"],
                "row_index": row_index_base + local_row_idx + 1,  # matches the 1-based row_index used below for pv_row
            })
        )
    # ... existing rows_polys loop (unchanged) ...
```

This costs nothing performance-wise (same data, one extra int per feature) and doesn't change anything the 2D view or PDF currently rely on.

## Fix — Part 2: consume per-table geometry in 3D, grouped by row (frontend)

In `terrain3dScene.ts`:

1. Keep `parseLayoutRows()` exactly as-is for **structure** (posts + torque tube positions) — it's correct and cheap.
2. Add a new `parseLayoutTables()` that reads `kind === "pv_module"` features, groups them by `properties.row_index`, and for each builds an `OrientedRow`-shaped record via `orientedRowFromRing()` (already handles arbitrary polygons). **Filter degenerate fragments here** — this is the actual fix for the old "collapse" bug: skip any table whose computed `length < 0.3` or `width < 0.2` (real clipped slivers, not real tables) instead of abandoning per-table parsing altogether.
3. In `buildTerrain3DScene()`, replace the single `BoxGeometry(row.length, ...)` per row (lines ~375 and ~419) with one small `BoxGeometry` per table feature in that row's group, each positioned/rotated independently using the row's `angle` and the table's own centroid (via `toThreePosition`). Posts and torque tube stay driven by the row-level structure from step 1 — only the table surfaces themselves get segmented.
4. **Texture fix while you're in there:** `createModuleTableTexture(row.nModules)` is currently called once per row (`terrain3dScene.ts:323`), creating a new `<canvas>`/`CanvasTexture` every time even though `modules_per_string` is a fixed project-level setting — every table has the same column count. Hoist this to **one shared texture built once per scene build**, not per row/table. Saves GPU memory and avoids the perf cliff that likely contributed to the original "collapse" symptom on large layouts.
5. **Use `THREE.InstancedMesh`** for both the table boxes and the posts instead of one `THREE.Mesh` per item. With ~700+ tables and 2-3 posts each on a 19,852-module site like the one in your screenshot, individual meshes is the kind of thing that visibly drops frame rate or stutters on orbit. `InstancedMesh` with a shared geometry/material and a `Matrix4` set per instance (`setMatrixAt`) handles thousands of instances at effectively no extra cost.

## Fix — Part 3: make poles visible without faking the geometry

In `Terrain3DView.tsx`, no structural change needed — the geometry is already correct. Two cheap additions:
- Bump post radius slightly (`terrain3dScene.ts` post `CylinderGeometry` radii, currently 0.06–0.09 / 0.07–0.09) to ~0.10–0.13 purely for on-screen legibility at typical zoom levels — note in a comment this is a visualization exaggeration, not the true post diameter.
- Add a "Show structure" toggle next to "Terrain mesh wireframe" (`Terrain3DView.tsx:108-118`) that sets table material `opacity` to ~0.85 with `transparent: true` when checked, so posts and the torque tube are visible through the tables without changing any real geometry.

## Out of scope — don't touch unless separately asked
Fixed-tilt tilt-angle logic, `MAX_3D_ROWS` cap, GLB export changes, any backend change to `inter_string_gap_m` itself or module spacing defaults.

## Verify after deploying
1. Reload the 3D view on the same Gut Rodau-style layout from the screenshot — each row should now show visible breaks every ~modules_per_string × module width, matching the 2D view's table boundaries.
2. Confirm post/torque-tube positions didn't shift (they're still driven by `pv_row`, untouched).
3. Load a large layout (close to `MAX_3D_ROWS` / thousands of modules) and confirm orbit/zoom stays smooth — this is the real test that `InstancedMesh` did its job.
4. Toggle "Show structure" and confirm posts/tube read clearly through the semi-transparent tables.
