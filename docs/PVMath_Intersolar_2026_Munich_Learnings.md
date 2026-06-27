# Intersolar Europe 2026 (Munich) — Field Learnings

**Recorded by:** Mohammed Ismail Pasha
**Captured:** 2026-06-25
**Status:** Living document — append new recollections at the bottom of the numbered list, in the order they come back to you. Don't reorder past entries; add a date stamp if a later addition arrives on a different day.

---

## Raw learnings (in the order received)

1. **An Ideematec Product Manager is building a higher-intelligence BOM/procurement tool.** Input is a 2D layout file exported from PVcase (`.pvc`); output is the full Main BOM with every line item ready for procurement — web/cloud-based.

2. **Terrain data challenge — solved with adaptive mesh density.** When asked about importing accurate terrain data, he said he uses a very fine mesh near pile/post positions and a coarser mesh everywhere else, rather than one uniform resolution across the site.

3. **A solver auto-optimizes tracker pile height.** He has an optimization algorithm that automatically raises/lowers (depresses) tracker heights across the site to converge on the best terrain-following solution, and from that derives the ideal pile length to manufacture for each post.

4. **He's using Claude plus paid Cesium terrain data — and is more accurate than our Copernicus 30m.** He pays for Cesium World Terrain access and gets meaningfully better elevation accuracy than our current Copernicus GLO-30 source. He raised the idea that there should be a paid route to buying topo data directly from local/national surveying authorities for the most accurate terrain possible.

5. **PVcase is building a SiteIQ-equivalent — and releasing it free.** Confirmed directly with PVcase that they're developing a site-screening tool similar to SiteIQ, planned as a free service.

6. **Viritech's (Virto) CAD-based planning tool is weak.** Observed it directly at their booth — poor relative to what's needed in this space.

7. **Our current module set is behind market expectations.** Conversations made clear competitors are already answering questions SiteIQ/TerrainIQ/YieldIQ don't yet touch — e.g. distance/connection feasibility to the nearest substation, and project financial modeling.

8. **Glint Solar is the closest comparable — and ahead of us.** Met them on day 2. They run on AWS S3 with a clean, well-organized data library, and their site analysis includes AI-generated imagery and similar polish. Assessed as more advanced than PVMath currently.

9. **An ex-colleague flagged RatedPower as a BayWa-facing competitor — but terrain extraction is still our edge.** Gave a demo; the feedback was that RatedPower offers a similar service for BayWa, but no competitor has yet built out terrain extraction as a real feature — it's still just an add-on differentiator in PVMath's favor.

10. **YieldIQ question: does it cover 1P/2P only, or also 3P/4P fixed-tilt configurations?** Raised by a prospect during a demo — open product question, not yet answered.

11. **Need to invest real budget in UI polish.** Clear signal from the expo that the platform needs to look and feel premium — current Streamlit-based UI doesn't read as premium next to competitors.

12. **Streamlit's results-page layout is a specific UX problem.** After running an analysis, the page loads scrolled down in a way that shows a malformed/empty view first, with the actual results appearing further down/to the side. Needs a faster, better-organized layout with more representative, monochrome-styled charts.

13. **Consolidate SiteIQ/TerrainIQ/YieldIQ into one flow.** Running three separate modules with three separate inputs doesn't match how competitors present their tools. Direction: one input, one report, with a Quick Mode / Full Mode toggle rather than three standalone tools.

14. **Layout is now considered non-negotiable for the platform to be viable** — without it, PVMath isn't competitive. Ismail has Ideematec's permission to build this independently: Ideematec said they are not a software company and have no interest in this space, so they're fine with him proceeding.

15. *(Placeholder — add further recollections here as they surface, each as a new numbered entry.)*

---

## Strategic implications (synthesis, not part of the raw record)

**Competitive position.** The market moved faster than expected on site-screening basics — PVcase is commoditizing free site screening, Glint Solar is ahead on data infrastructure and AI-generated visuals, and RatedPower is already embedded with at least one major developer (BayWa). PVMath's defensible wedge right now is genuinely narrow: terrain extraction/CAD export (point 9) and the emerging layout capability (point 14) are the two things nobody else at the show had. That argues for leaning harder into terrain + layout as the core pitch rather than competing head-on with PVcase's free screening tier.

**Terrain data accuracy gap.** Ideematec's PM is getting materially better elevation accuracy from paid Cesium data than PVMath's free Copernicus GLO-30 source (point 4). This is worth treating as a real, quantifiable gap — worth scoping what a Cesium (or equivalent paid DEM) integration would cost and whether it's justified once paying customers are testing terrain-sensitive use cases (cut/fill, pile length). This also connects directly to the still-open TerrainIQ georeferencing/accuracy conversation from earlier this week.

**Product consolidation (point 13) and layout (point 14) are now the two highest-leverage roadmap items** — both are described by the market as gating issues, not nice-to-haves. Given LayoutIQ is currently admin-only per the roadmap, point 14 effectively elevates it from "future module" to "near-term priority," and the Ideematec permission removes what had been an open legal question on competitive overlap with his employer (worth getting that confirmation in writing at some point, even informally over email, given it shapes both Nebentätigkeit and any future IP discussion — but functionally this resolves the concern raised earlier this week about UG formation and side-business consent).

**UI/UX (points 11, 12) is a credibility tax, not cosmetics.** Premium-feeling output is apparently table stakes among the Glint Solar / PVcase / RatedPower tier PVMath is being compared against. Worth scoping as a discrete workstream (through Cursor) separate from new features — fixing the post-analysis scroll/layout bug alone may address a chunk of the "not premium" perception.

**Open product question (point 10)** — 3P/4P fixed-tilt support in YieldIQ — needs an answer; flag to Cursor/product backlog if not already covered.

---

*Append new points below as they're recalled. Keep this file as the single source of truth for Intersolar 2026 learnings; pull individual items into STATUS.md or the roadmap once a decision is made on each.*
