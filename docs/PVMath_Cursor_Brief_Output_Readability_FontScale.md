# Cursor Brief — Output page text too small (global font scale)

**Requested by:** Mohammed Ismail Pasha, 2026-06-28
**Symptom:** On the SiteIQ output/results page (Site screening metrics, Monthly GHI chart, Intelligent GIS Analysis table), text is hard to read — especially the GHI chart's bar values, month labels, and axis title, plus the metric card eyebrow labels and hint/table text.

**File touched:** `frontend/src/index.css`

---

## Root cause (confirmed in code)

There is no root font-size override anywhere in the app (`html`/`body` rely on the browser default, 16px), and almost every text size on this page is set in `rem` units that are already small relative to that base:

- `.ghi-bar-value` (chart values, e.g. "140") — `0.62rem` ≈ 9.9px (`index.css:1346`)
- `.ghi-xlabel` (month labels) / `.ghi-xaxis-title` / `.ghi-yaxis-title` — `0.66rem` ≈ 10.6px (`index.css:1252, 1353, 1362`)
- `.ghi-ytick` (chart y-axis numbers) — `0.68rem` ≈ 10.9px (`index.css:1272`)
- `.metric .label` (e.g. "SOLAR", "FLOOD") — `0.75rem` = 12px, plus uppercase + letter-spacing which reduces legibility further (`index.css:1398`)
- `.metric .sub`, `.hint` (descriptive lines under metrics) — `0.82rem` ≈ 13px (`index.css:1411, 1430`)
- `.gis-summary-table`, `.gis-setback-input` (Constraint/Features/Setback/Excluded table) — `0.82rem` ≈ 13px (`index.css:3171, 3198`)

Because everything is `rem`-based, a single root font-size change scales the whole app proportionally without touching any of these individual rules.

## Fix

Add a root font-size to `:root` (or a new `html` rule) near the top of `index.css`, just under the existing `:root` block (`index.css:1-16`):

```css
html {
  font-size: 17px; /* was browser default 16px — scales all rem-based text app-wide */
}
```

That's the entire change. `17px` is a conservative bump (~6%); if it still reads small after testing, `18px` (~12.5%) is the next reasonable step.

## Out of scope — don't touch unless separately asked

Any individual font-size value in `index.css` — this brief is the global-lever approach (one line), not a targeted per-element rewrite. Layout/spacing rules, color, or anything unrelated to text size.

## Verify after deploying

1. Open the SiteIQ output page (Site screening, Monthly GHI chart, Intelligent GIS Analysis) and confirm the chart values/labels and metric/table text are visibly larger and easier to read.
2. Check 2–3 other pages/screens (Project Setup, account/billing panels, LayoutIQ sidebar) for any text that now wraps awkwardly, overflows its container, or causes a button/label to clip — the bump is global, so anything tightly sized elsewhere could be affected.
3. Quick check on a smaller laptop screen width (e.g. 1366px) to confirm nothing that fit before now overflows or causes horizontal scroll.
4. If everything still looks comfortably sized but no layout breaks, this is good to ship as-is; if it still feels small, bump `17px` → `18px` and repeat steps 1-3.
