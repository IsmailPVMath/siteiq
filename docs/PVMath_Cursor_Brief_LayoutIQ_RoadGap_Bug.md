# Cursor Brief — Road presets insert extra, irregular gaps near boundary edges

**Requested by:** Mohammed Ismail Pasha, 2026-06-28
**Symptom:** With any road preset active (e.g. "SAT auto — 2 rows + 5m N-S gap", pitch 7.01 m), the layout shows 2 trackers placed correctly, then a gap far bigger than the expected 5 m road — and the oversized gaps cluster right along the diagonal property-line/restriction edge in the screenshot, not uniformly across the field. With "No roads" the same parcel lays out fine.

**File touched:** `layoutiq/engine.py`

---

## Root cause (confirmed in code)

`run_layout()`'s row sweep (`layoutiq/engine.py`) walks y in `pitch` steps and uses a counter `rows_in_block` to decide when to insert the N-S road gap:

```python
# line ~544 — band produced no usable segments (e.g. clipped away by a
# diagonal boundary, restriction zone, or slope-limit exclusion)
if not segments:
    y += pitch
    rows_in_block += 1                       # <-- counted even though nothing was placed
    if use_blocks and rows_in_block >= rows_per_block:
        y += block_gap_m                     # <-- road inserted in empty space
        rows_in_block = 0
    continue
```

```python
# line ~646 — bottom of the loop, after attempting to place real rows
y += pitch
rows_in_block += 1                           # <-- counted even if every segment in
if use_blocks and rows_in_block >= rows_per_block:   #     this band was skipped below
    y += block_gap_m
    rows_in_block = 0
```

`rows_in_block` is meant to count **rows actually placed**, so a road appears every N real rows. Instead it counts **loop iterations** (grid band positions), whether or not a row was placed there. Inside the `for seg_min, seg_max in segments:` loop (lines ~552-644) there are three separate `continue`s that skip a segment without ever appending to `rows_data` — too-short segment (554-555), zero strings fit (579-580), and clipped area too small (587-588) — none of them are reflected in the counter.

Near any irregular edge — a diagonal property line, a restriction polygon, or "Exclude SAT zones above slope limit" — many consecutive bands legitimately produce empty or undersized segments. The counter keeps advancing through all of them anyway, so every `rows_per_block` (2) iterations — real or empty — it fires another `block_gap_m` (5 m) insertion. Along a stretch of 8-10 empty bands that's 4-5 stacked 5 m insertions landing in space with no rows at all, and the next real row only resumes after all of that — which is exactly the "2 trackers, then a huge gap" pattern in your screenshot, concentrated right along the diagonal edge.

With "No roads" selected, `use_blocks` is `False` (`rows_per_block=0` from the `no_roads` preset in `layoutiq/defaults.py`), so this code path never triggers — consistent with why disabling roads "fixes" it.

## Fix

Only advance `rows_in_block` (and only fire `block_gap_m`) when a row was actually placed in that band — not on every loop iteration.

```python
while y + row_ns <= maxy + 1e-6:
    ...
    if not segments:
        y += pitch
        continue                              # removed: rows_in_block += 1 / block_gap_m here

    row_placed_this_band = False               # new, right before the segments loop

    for seg_min, seg_max in segments:
        ...
        rows_data.append({...})
        row_placed_this_band = True            # new, right after the existing rows_data.append(...)

    y += pitch
    if row_placed_this_band:                   # new guard
        rows_in_block += 1
        if use_blocks and rows_in_block >= rows_per_block:
            y += block_gap_m
            rows_in_block = 0
```

This is a small, local change — `rows_in_block` now only ticks up when a real row exists, so a road appears every 2 *actual* rows regardless of how many empty/skipped bands sit in between. No schema or output-shape change; `rows_data`, `rows_polys`, `string_polys` are unaffected.

## Out of scope — don't touch unless separately asked
`_ew_road_bands()` / E-W (cross-tracker) road logic — same file but a separate code path, not implicated by this symptom. Preset values themselves (2 rows / 5 m, etc.) in `layoutiq/defaults.py`.

## Verify after deploying
1. Re-run the same parcel from the screenshot with "SAT auto — 2 rows + 5m N-S gap" — gaps along the diagonal boundary should now match the uniform ~12 m (7.01 m pitch + 5 m road) spacing seen elsewhere in the field, not multiples of it.
2. Confirm a parcel with **no** irregular edges (simple rectangle) still places identical roads before/after — this fix should be a no-op there since every band already places a row.
3. Confirm "No roads" output is byte-for-byte unchanged (that path doesn't touch this code).
4. Try the "8m" and "1 row + 5m" presets on the same irregular parcel and confirm gaps are now also uniform.
