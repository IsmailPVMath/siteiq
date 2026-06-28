# Cursor Brief — Clean up the KMZ parcel/layers panel (spacing, scroll, names)

**Requested by:** Mohammed Ismail Pasha, 2026-06-27
**Symptom:** After importing a KMZ with many layers (screenshot: 66/66 parcels across groups like ProjectBoundary, Buildable Area, Laydown – Permanent, SiteFence), the parcel panel looks messy — rows feel cramped/overlaid, there's no obvious way to scroll, and child rows are labeled redundantly (e.g. "Buildable Area / Unnamed (6)" repeating the group name it's already nested under).

**Files touched:** `pvmath_kml.py`, `frontend/src/index.css`, `frontend/src/pages/ProjectSetupPage.tsx`, `frontend/src/components/project-setup/BoundaryWorkspace.tsx`

## Good news first

Collapse/uncollapse and per-parcel/per-group delete are **already implemented and wired correctly** — `onToggleGroupCollapsed`, `onRemoveGroup`, `onRemoveParcel` in `ProjectSetupPage.tsx:471-485` all work, and the caret (▾/▸) and × buttons render correctly in `BoundaryWorkspace.tsx:118-147`. The panel also already has `overflow-y: auto` (`index.css:2106-2113`). None of that is broken — the problem is sizing, density, and naming, not missing functionality.

## Root cause 1 — redundant names baked in server-side

`pvmath_kml.py`'s `_display_name()` (lines 97-108) deliberately prefixes the *parent folder name* whenever the placemark's own name matches the "Unnamed" pattern:

```python
if len(parts) >= 2 and _UNNAMED_RE.search(parts[-1]):
    return f"{parts[-2]} / {parts[-1]}"
```

That's why a placemark with no `<name>` inside the "Buildable Area" folder becomes `"Buildable Area / Unnamed (6)"`. This value flows straight through to the UI: `api/routers/boundary.py:53` (`feat.get("display_name") or feat.get("name") or ...`) is the only place that picks the row label, and the frontend renders it verbatim as `parcel-name` (`BoundaryWorkspace.tsx:158`). Since the panel already shows the group name once in the group header, every child row repeating it is pure visual noise — it's a big part of why the list reads as cluttered.

**Fix:** in `_display_name()`, when the last segment is an "Unnamed" placeholder, drop the parent-folder prefix and use a friendlier counter instead of leaking the literal KML fallback string:

```python
if len(parts) >= 2 and _UNNAMED_RE.search(parts[-1]):
    m = re.search(r"\((\d+)\)", parts[-1])
    return f"Parcel {m.group(1)}" if m else "Parcel 1"
return parts[-1]
```

(Verify this doesn't regress the one other caller of `display_name`, `pvmath_kml.py:519` — it just falls back to `f["name"]` if `display_name` is falsy, so an empty/short string is safe there too.)

## Root cause 2 — scroll box too small and not discoverable

`.parcel-groups` (`index.css:2106-2113`) caps at `max-height: 280px`. For a 66-parcel KMZ where one group alone ("Buildable Area") holds 36 children, that's a tiny window to scroll through, and the default OS/browser scrollbar (especially macOS auto-hiding overlay scrollbars) gives no visual hint there's more below — so it just looks clipped/broken rather than scrollable.

**Fix:**
```css
.parcel-groups {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;              /* was 0.4rem — more breathing room between groups */
  max-height: min(58vh, 460px); /* was 280px — scales with viewport, much roomier */
  overflow-y: auto;
  padding-right: 0.3rem;
  scrollbar-gutter: stable;
}
.parcel-groups::-webkit-scrollbar { width: 8px; }
.parcel-groups::-webkit-scrollbar-thumb {
  background: #c3d6cb;
  border-radius: 4px;
}
```
Also bump `.parcel-list li` padding (`index.css:2142-2151`) from `0.3rem 0.55rem` to `0.4rem 0.6rem` for less cramped rows.

## Root cause 3 — everything lands expanded on import

`collapsedGroups` starts as `{}` (`ProjectSetupPage.tsx:68`), so right after a KMZ with many groups loads, every group is expanded simultaneously — a 66-parcel import dumps all rows at once instead of giving you a clean overview to drill into.

**Fix:** in the file-upload handler (`onBoundaryFile`, wherever it sets `draft.geometry.parcels` after parsing — find it via the `onFileUpload` prop wiring at `ProjectSetupPage.tsx:448`), after parcels are populated, default every group except the first to collapsed:
```ts
const groups = Array.from(new Set(parsedParcels.map((p) => p.layer_group || "Other")));
setCollapsedGroups(Object.fromEntries(groups.map((g, i) => [g, i > 0])));
```
Also add "Expand all" / "Collapse all" buttons next to "Clear" in `.parcel-manager-head` (`BoundaryWorkspace.tsx:101-108`), wired to set every key in `collapsedGroups` to `false`/`true` at once — cheap, and directly solves "can't quickly tidy up a big import."

## Out of scope — don't touch unless separately asked
The grouping logic itself (`boundary_layer_group()`), the infrastructure-layer exclusion regexes, per-parcel enable/disable behavior, the "Site areas only" smart-select button.

## Verify after deploying
1. Re-import the same KMZ from the screenshot — child rows under "Buildable Area" should read "Parcel 6" / "Parcel 7" instead of "Buildable Area / Unnamed (6)".
2. Confirm the panel now shows a visible scrollbar and a noticeably taller window before clipping.
3. Confirm only the first group is expanded right after import; others start collapsed.
4. Click Expand all / Collapse all and confirm every group responds.
5. Confirm delete (×) on a parcel and on a whole group still work exactly as before — this brief doesn't touch that logic.
