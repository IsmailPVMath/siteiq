"""Public engineering help — Level 1 (website) + Level 2 (in-app). No proprietary formulas."""

from __future__ import annotations

import streamlit as st

GUIDE_BASE = "https://pvmath.com/guides"


def guide_url(slug: str) -> str:
    return f"{GUIDE_BASE}/{slug}.html"


# slug → title, tooltip (one line), body (markdown, public-safe)
HELP: dict[str, dict[str, str]] = {
    # ── TerrainIQ ──
    "glo30": {
        "title": "Copernicus GLO-30 DEM",
        "slug": "glo30-and-5m-grid",
        "tooltip": "Global satellite elevation model — ~30 m native posting.",
        "body": (
            "Copernicus **GLO-30** is a free global digital elevation model with roughly "
            "**30 m horizontal detail**. TerrainIQ uses it for early terrain screening before "
            "LiDAR or RTK survey.\n\n"
            "**Limitation:** Features smaller than ~30 m (ditches, berms, rows) may not appear. "
            "Vertical accuracy is typically ±1–3 m RMSE in open terrain."
        ),
    },
    "grid_spacing": {
        "title": "Output grid spacing",
        "slug": "glo30-and-5m-grid",
        "tooltip": "Default 5 m layout grid — resampled from ~30 m source.",
        "body": (
            "The **5 m grid** is the spacing between analysis points inside your boundary. "
            "It makes slopes, contours, and CAD exports layout-friendly.\n\n"
            "It does **not** mean the satellite measured every 5 m — underlying GLO-30 "
            "detail remains ~30 m. Think of it as a finer graph paper over the same photo."
        ),
    },
    "mean_slope": {
        "title": "Mean slope",
        "slug": "mean-slope-vs-cross-row",
        "tooltip": "Average gradient across the site — primary screening metric.",
        "body": (
            "**Mean slope** is the average terrain gradient (%) over all valid points in "
            "your boundary. It summarizes overall constructability.\n\n"
            "For **single-axis trackers**, mean slope alone can mislead — check "
            "**cross-row slope** for row-to-row grade changes."
        ),
    },
    "max_slope": {
        "title": "Maximum slope",
        "slug": "mean-slope-vs-cross-row",
        "tooltip": "Steepest single grid cell — flags localized problem areas.",
        "body": (
            "**Max slope** is the steepest point on the analysis grid. A low mean slope "
            "with a high max slope often means isolated steep strips (ridges, cuts) "
            "that need review in layout or grading."
        ),
    },
    "cross_row_slope": {
        "title": "Cross-row slope",
        "slug": "mean-slope-vs-cross-row",
        "tooltip": "Grade perpendicular to tracker rows — clearance driver.",
        "body": (
            "**Cross-row slope** measures grade **across** tracker row direction. "
            "Large cross-row changes drive structural clearance, drainage, and grading cost.\n\n"
            "PVMath flags tracker sites when cross-row statistics suggest **review zones** "
            "even if mean slope looks excellent."
        ),
    },
    "terrain_score": {
        "title": "Terrain score",
        "slug": "terrainiq-metrics",
        "tooltip": "Summary 0–100 terrain index for executives — screening only.",
        "body": (
            "The **Terrain Score** compresses slope and tracker-relevant metrics into one "
            "number for quick communication.\n\n"
            "Use it for **go/no-go conversations**, not for pile design. Always read the "
            "engineering verdict and cross-row details alongside the score."
        ),
    },
    "terrain_verdict": {
        "title": "Engineering verdict",
        "slug": "terrainiq-metrics",
        "tooltip": "Qualitative suitability label for fixed tilt or tracker.",
        "body": (
            "The **engineering verdict** translates slope statistics into labels such as "
            "Excellent, Good, or Challenging — separately for **fixed tilt** and "
            "**single-axis tracker**.\n\n"
            "Tracker verdicts may include **Review Zones** when cross-row grades need "
            "clearance review despite favorable average slopes."
        ),
    },
    "cad_export": {
        "title": "CAD & GIS exports",
        "slug": "landxml-dxf-solar",
        "tooltip": "LandXML, DXF, CSV — screening-grade, download immediately.",
        "body": (
            "TerrainIQ exports a **CAD starter kit**: UTM LandXML surface, DXF contours with "
            "**parcel linework** on layer SITE_BOUNDARY, and reference JSON.\n\n"
            "USA projects receive **US Survey Feet** in georef files. Imports are "
            "screening-grade — verify critical grades with survey before FEED."
        ),
    },
    "screening_grade": {
        "title": "Screening-grade data",
        "slug": "screening-vs-survey",
        "tooltip": "Not a substitute for LiDAR, RTK, or bankable studies.",
        "body": (
            "**Screening-grade** means suitable for early site selection, client meetings, "
            "and layout exploration — not for stamped civil design or pile schedules.\n\n"
            "Commission **LiDAR or RTK** before FEED, procurement, and construction."
        ),
    },
    # ── SiteIQ ──
    "ghi": {
        "title": "Global Horizontal Irradiance (GHI)",
        "slug": "siteiq-screening",
        "tooltip": "Annual solar resource on a horizontal plane — PVGIS source.",
        "body": (
            "**GHI** is total solar radiation on a horizontal surface (kWh/m²/year), "
            "from **PVGIS (EC JRC)** — the same family of data used in pre-feasibility "
            "studies worldwide.\n\n"
            "SiteIQ uses GHI with optimal tilt or tracker yield proxies for screening."
        ),
    },
    "pvmath_score": {
        "title": "PVMath Score",
        "slug": "siteiq-screening",
        "tooltip": "Combined screening index — solar, terrain, flood, land, regulatory.",
        "body": (
            "The **PVMath Score** (0–100) combines multiple screening categories into one "
            "index for portfolio comparison and early go/no-go.\n\n"
            "It is a **deterministic screening model**, not a bankability rating. "
            "Category details appear in your PDF report."
        ),
    },
    "site_verdict": {
        "title": "Overall site verdict",
        "slug": "siteiq-screening",
        "tooltip": "Plain-language recommendation from combined screening.",
        "body": (
            "The **overall verdict** summarizes SiteIQ findings (solar, terrain, flood "
            "heuristic, land use, regulatory flags) into a single recommendation tier.\n\n"
            "Use alongside module-specific reports — TerrainIQ for terrain detail, YieldIQ "
            "for energy comparison."
        ),
    },
    "flood_risk": {
        "title": "Flood risk indicator",
        "slug": "siteiq-screening",
        "tooltip": "Elevation-based heuristic — not FEMA or hydraulic modelling.",
        "body": (
            "SiteIQ's **flood indicator** uses elevation context as a **quick flag**, "
            "not official flood-zone mapping.\n\n"
            "Always confirm with local hydrology studies, FEMA/National datasets, or "
            "country-specific flood products before investment decisions."
        ),
    },
    "regulatory_flags": {
        "title": "Regulatory flags",
        "slug": "siteiq-screening",
        "tooltip": "Country-aware pointers — not legal advice.",
        "body": (
            "**Regulatory flags** highlight common permitting or tariff contexts "
            "(e.g. EEG in Germany, Agri-PV notes) based on project country.\n\n"
            "These are **indicative pointers** for your checklist — not legal or "
            "planning approval."
        ),
    },
    # ── YieldIQ ──
    "specific_yield": {
        "title": "Specific yield",
        "slug": "yieldiq-yield",
        "tooltip": "Energy per kWp installed (kWh/kWp/yr) — PVGIS-based.",
        "body": (
            "**Specific yield** is annual energy output divided by DC capacity "
            "(kWh/kWp/year). It normalizes sites for fair comparison.\n\n"
            "YieldIQ values are **preliminary** — typically ±8–15% vs. bankable studies."
        ),
    },
    "performance_ratio": {
        "title": "Performance ratio (PR)",
        "slug": "yieldiq-yield",
        "tooltip": "System efficiency vs. ideal — includes losses.",
        "body": (
            "**Performance ratio** compares actual system output to ideal DC output "
            "under reference conditions. Lower PR means higher cumulative losses "
            "(temperature, soiling, inverter, wiring, etc.)."
        ),
    },
    "capacity_factor": {
        "title": "Capacity factor (CF)",
        "slug": "yieldiq-yield",
        "tooltip": "Utilization of nameplate capacity over a year.",
        "body": (
            "**Capacity factor** is annual energy divided by the theoretical maximum "
            "if the plant ran at full DC capacity 24/7. Utility-scale solar CF "
            "varies strongly by latitude and resource."
        ),
    },
    "gcr": {
        "title": "Ground coverage ratio (GCR)",
        "slug": "yieldiq-yield",
        "tooltip": "Module area vs. ground area — drives shading and DC density.",
        "body": (
            "**GCR** is the ratio of module collection area to ground footprint. "
            "Higher GCR increases DC density but raises **row shading** losses.\n\n"
            "YieldIQ models shading from your GCR sliders. **Capacity screening** "
            "uses a standard GCR band for MWp/ha estimates across PVMath modules."
        ),
    },
    "yield_screening": {
        "title": "Screening vs analysis profile",
        "slug": "yieldiq-yield",
        "tooltip": "YieldIQ uses PVGIS screening settings — not bankable.",
        "body": (
            "YieldIQ runs **PVGIS** with disclosed loss assumptions for **four "
            "configurations** (fixed/tracker × 1P/2P).\n\n"
            "Results support **configuration choice** early in development — not "
            "substitute for PVsyst, DNV, or lender-grade yield assessment."
        ),
    },
    "shading_loss": {
        "title": "Row shading loss",
        "slug": "yieldiq-yield",
        "tooltip": "Estimated from GCR — engineering approximation.",
        "body": (
            "**Shading loss** in YieldIQ is estimated from row geometry (GCR) using "
            "standard engineering approximations. Trackers model **backtracking** "
            "benefit vs. fixed tilt at the same GCR.\n\n"
            "Detailed hourly shading requires project-specific layout and may differ."
        ),
    },
}


def help_popover(key: str, label: str = "ⓘ") -> None:
    """In-app help popover — public content only."""
    topic = HELP.get(key)
    if not topic:
        return
    with st.popover(label):
        st.markdown(f"**{topic['title']}**")
        st.markdown(topic["body"])
        st.link_button(
            "Read full guide →",
            guide_url(topic["slug"]),
            use_container_width=True,
        )


def help_caption(*keys: str) -> None:
    """One-line help links below a section."""
    parts = []
    for key in keys:
        t = HELP.get(key)
        if t:
            parts.append(f"[{t['title']}]({guide_url(t['slug'])})")
    if parts:
        st.caption("ⓘ " + " · ".join(parts))


def help_section_header(title: str, *keys: str) -> None:
    """Section header row with help popovers."""
    cols = st.columns([5] + [1] * len(keys))
    cols[0].markdown(f"**{title}**")
    for col, key in zip(cols[1:], keys):
        with col:
            help_popover(key, "ⓘ")
