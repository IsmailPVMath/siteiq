"""100 LinkedIn post ideas + 90-day publishing calendar generator."""

from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

from pvmath_marketing.brand import AUDIENCES, BRAND, HASHTAG_POOLS

CATEGORIES = [
    ("Educational", "education", 11),
    ("Industry insights", "industry", 11),
    ("Founder journey", "founder", 10),
    ("Product updates", "product", 11),
    ("Customer pain points", "pain", 11),
    ("Case studies", "case", 9),
    ("Terrain and GIS topics", "terrain", 13),
    ("Yield analysis topics", "yield", 13),
    ("Solar development economics", "economics", 11),
]

IDEA_SEEDS: dict[str, list[tuple[str, str, str]]] = {
    "education": [
        ("GLO-30 vs 5 m grid", "Copernicus posts at ~30 m. Your layout grid can be 5 m.", "Explain resampling vs sensor resolution before FEED."),
        ("Mean vs cross-row slope", "Mean slope flat. Trackers still need cross-row review.", "Link to cross-row p95 for SAT clearance talks."),
        ("Screening vs survey", "Screening answers go/no-go. Survey answers design.", "List what LiDAR and bankable yield still decide."),
        ("GCR and shading", "Higher GCR increases DC density and row shading.", "Compare configs at same GCR in YieldIQ."),
        ("Agri-PV density", "Agri-PV uses lower MWp/ha bands by design.", "Dual-use is not standard ground-mount density."),
        ("PVMath Score limits", "Portfolio index ≠ bankability.", "Use score for ranking; confirm with studies."),
        ("US Survey Feet CAD", "US georef exports need imperial drawing import.", "No extra feet↔metre scaling after import."),
        ("Flood heuristics", "Elevation flags are not FEMA maps.", "Always confirm with local hydrology."),
        ("PVGIS screening profile", "SiteIQ and YieldIQ use different depth.", "Same coordinate, different loss assumptions."),
        ("KMZ to CAD path", "Boundary only is not a civil surface.", "LandXML + SITE_BOUNDARY linework workflow."),
        ("Tracker backtracking", "SAT shading model differs from fixed at same GCR.", "Configuration choice before detailed layout."),
        ("Indicative MWp/ha", "Screening density ≠ as-built layout.", "Layout-optimised designs change DC footprint."),
    ],
    "industry": [
        ("LiDAR timing", "Order LiDAR when the site earns it.", "Shortlist with GLO-30 first."),
        ("EPC handoff friction", "Land and engineering use different tools.", "Standardise screening outputs."),
        ("Germany screening culture", "DACH teams expect documented pre-feasibility.", "PDF + disclaimers matter."),
        ("Spain resource sites", "High GHI does not remove terrain risk.", "Screen slope before option fees."),
        ("India utility-scale pace", "Fast pipelines still pay for skipped terrain.", "Global DEM + PVGIS screening."),
        ("GCC tracker adoption", "SAT dominates where terrain allows.", "Cross-row metrics early."),
        ("Agri-PV permitting", "Land use category changes the path.", "Regulatory flags as checklist."),
        ("Interconnection queue reality", "Resource screening is table stakes.", "Differentiate on constructability data."),
        ("Module procurement cycles", "Early yield config reduces rework.", "Fixed vs tracker before BOM freeze."),
        ("Data centre load boom", "Greenfield speed vs engineering rigour.", "Screening layer balances both."),
        ("ESG reporting pressure", "Document screening methodology.", "Deterministic models beat black boxes."),
        ("Subcontractor civil scope", "Give civil CAD starter geometry.", "Reduce redraw from KMZ."),
    ],
    "founder": [
        ("Why I started PVMath", "Same pre-feasibility pack rebuilt too many times.", "Side project alongside EPC job."),
        ("Build in public", "Shipping screening honesty over feature count.", "Ask EPCs what hurts next."),
        ("No dark scores", "We publish guides, not weights.", "Knowledge Centre over hype."),
        ("Ground-mount only", "Focus beats breadth for v1.", "Fixed, tracker, Agri-PV."),
        ("Frugal stack", "Railway + Supabase + open datasets.", "Professional outputs on lean infra."),
        ("Customer feedback loop", "Civil 3D import edge cases shaped exports.", "Contour clipping shipped."),
        ("Pro manual gate", "Customer docs without IP leak.", "Public vs internal split."),
        ("Roadmap discipline", "RevenueIQ when it meets screening bar.", "Not before."),
        ("Weeknight engineering", "Features from real project pain.", "Founder-led product."),
        ("Global from day one", "PVGIS + GLO-30 worldwide.", "Not DACH-only tooling."),
    ],
    "product": [
        ("SiteIQ PDF", "One report for internal gate.", "Solar + terrain + flags."),
        ("TopoIQ ZIP", "LandXML + georef DXF + reference JSON.", "Download immediately after run."),
        ("YieldIQ four configs", "1P/2P × fixed/tracker.", "Compare at your GCR."),
        ("Project Setup once", "All modules inherit boundary.", "Stop re-entering coordinates."),
        ("Knowledge Centre", "Public engineering guides.", "SEO + sales enablement."),
        ("In-app help links", "ⓘ tips to guides.", "No 300-page PDF on homepage."),
        ("Free tier", "5 runs per module monthly.", "Try on real boundary."),
        ("Professional tier", "50 runs + engineering manual.", "Teams in active pipelines."),
        ("Contour clip fix", "CAD exports respect parcel.", "No grid edge spikes."),
        ("TopoIQ cross-row", "Tracker verdict review zones.", "Beyond mean slope."),
        ("SiteIQ regulatory flags", "Country-aware pointers.", "Not legal advice."),
        ("Yield cross-ref", "Modules reference each other.", "Consistent location context."),
    ],
    "pain": [
        ("Bad terrain late", "Slope surprise after option payment.", "TopoIQ before commitment."),
        ("Inconsistent yield", "Different GCR in every spreadsheet.", "YieldIQ normalises comparison."),
        ("KMZ-only handoff", "Civil redraws everything.", "CAD export package."),
        ("Portfolio chaos", "50 pins, no ranking method.", "SiteIQ + score conversation."),
        ("Black-box AI scores", "Executives want numbers engineers distrust.", "Deterministic screening."),
        ("Mean slope trap", "Rolling sites look flat.", "Cross-row p95."),
        ("Premature LiDAR", "Budget burned on rejected sites.", "Screen first."),
        ("Mixed local/georef CAD", "Geometry miles from surface.", "Georef-only for map work."),
        ("Oversold DEM", "5 m claimed as LiDAR-grade.", "We disclose ~30 m native."),
        ("Bankability too early", "Screening labelled as DNV.", "Honest yield limits."),
        ("Multi-parcel seams", "Disconnected parcels in one KMZ.", "TIN breaklines explained."),
        ("Lost screening disclaimers", "Client thinks PDF is sign-off.", "Footer on every export."),
    ],
    "case": [
        ("Texas rolling site", "Mean slope good; cross-row flagged review.", "LiDAR scoped to problem zones."),
        ("Spain high GHI", "Resource strong; terrain screening still ran.", "Go with grading note."),
        ("Germany Agri-PV", "Lower density band applied.", "Regulatory checklist started."),
        ("India pin screening", "No boundary yet; sparse terrain sample.", "TopoIQ confirmed after KMZ."),
        ("100 MWp config choice", "SAT 1P +17% vs fixed at screening GCR.", "PVsyst later for bankable."),
        ("EPC CAD workflow", "Georef LandXML in Civil 3D.", "SITE_BOUNDARY on correct layer."),
        ("Portfolio week", "12 sites screened; 3 advanced.", "Time saved vs manual pack."),
        ("Investor meeting", "PDF + honest limits.", "Screening framed correctly."),
        ("USA imperial CAD", "US Survey Feet import.", "No scaling error."),
        ("Rejected site early", "Flood flag + steep max slope.", "Avoided survey spend."),
    ],
    "terrain": [
        ("Copernicus GLO-30", "Free global DEM for screening.", "Limits documented."),
        ("5 m layout grid", "Finer graph paper, same photo.", "Layout-friendly contours."),
        ("Slope map colours", "Green flat, red steep.", "Executive + engineering views."),
        ("Engineering verdict tiers", "Fixed vs tracker labels.", "Review zones for SAT."),
        ("Terrain score use", "Executive summary only.", "Read drivers table."),
        ("LandXML UTM", "Map-aligned surface.", "CoordinateSystem in file."),
        ("Local centroid DXF", "Quick layout near origin.", "Not for geolocation."),
        ("Parcel linework layer", "SITE_BOUNDARY in DXF.", "Not standalone boundary file."),
        ("Slope PDF map", "North arrow + scale.", "Client-ready terrain page."),
        ("Multi-parcel export", "Merged TIN warning.", "Continuous boundary tip."),
        ("OpenTopoData vs GLO-30", "SiteIQ sparse vs TopoIQ confirmed.", "When to run TopoIQ."),
        ("Grid auto-coarsen", "Huge sites optional coarsen.", "Default 5 m for layout."),
        ("Gaussian smooth slopes", "DEM noise handling.", "Screening not survey."),
        ("Terrarium tiles", "AWS elevation source.", "Disclosed in docs."),
    ],
    "yield": [
        ("Specific yield compare", "kWh/kWp/yr normalises sites.", "YieldIQ table output."),
        ("PR interpretation", "System efficiency index.", "Not standalone bankability."),
        ("Capacity factor", "Utilisation of nameplate.", "Latitude dependent."),
        ("POA vs GHI", "Plane-of-array for mount type.", "PVGIS sourced."),
        ("Temperature loss", "PVGIS physics derate.", "Not flat percentage guess."),
        ("Soiling slider", "User assumption disclosed.", "Screening sensitivity."),
        ("Tracker gain %", "SAT vs fixed same GCR.", "Early config dialogue."),
        ("2P vs 1P portrait", "Four configs compared.", "Density vs shading trade."),
        ("Annual MWh with area", "When boundary area known.", "Capacity × yield link."),
        ("PVsyst handoff", "Screening narrows config.", "Bankable model later."),
        ("ERA5 database", "PVGIS raddatabase note.", "Location consistent."),
        ("Loss stack honesty", "Total loss from PVGIS l_total.", "Not user subtotal alone."),
        ("Screening ± range", "±8–15% vs bankable typical.", "Set client expectations."),
        ("GCR band capacity", "MWp/ha screening band.", "Separate from yield GCR."),
    ],
    "economics": [
        ("MWp/ha screening", "Standard vs Agri-PV bands.", "Mount type matters."),
        ("Option fee timing", "Screen before land payment.", "Risk reduction."),
        ("LiDAR cost avoidance", "Skip on rejected terrain.", "Direct savings."),
        ("Engineering hours", "Rebuild pre-feasibility pack.", "Automation value."),
        ("Portfolio prioritisation", "Rank before deep spend.", "Score as conversation tool."),
        ("Tracker capex vs yield", "Config choice affects LCOE path.", "YieldIQ early compare."),
        ("Grading unknowns", "Terrain screening flags review.", "Civil budget contingency."),
        ("Interconnection study order", "After site shortlist.", "Screening supports list."),
        ("EPC bid preparation", "Shared screening PDF.", "Less rework in DD."),
        ("Investor DD pack", "Screening ≠ bankable.", "Frame correctly."),
        ("Agri-PV revenue stack", "Future RevenueIQ module.", "Screening today."),
        ("Currency of trust", "Engineers trust disclaimers.", "Honesty converts."),
        ("Free tier ROI", "5 runs prove workflow.", "Upgrade when pipeline active."),
        ("Developer seat economics", "Team tier for volume.", "250 runs/module."),
    ],
}


def _cta_for_category(cat_key: str) -> str:
    ctas = {
        "education": f"Read the guide: {BRAND['guides']}",
        "industry": f"How does your team screen today? {BRAND['website']}",
        "founder": f"Follow the build: {BRAND['website']}",
        "product": f"Try free: {BRAND['app_url']}",
        "pain": f"Screen before survey spend: {BRAND['app_url']}",
        "case": f"Run your anonymised site: {BRAND['app_url']}",
        "terrain": f"TopoIQ guide: {BRAND['guides']}landxml-dxf-solar.html",
        "yield": f"YieldIQ on your coordinates: {BRAND['app_url']}",
        "economics": f"Compare plans: {BRAND['website']}#pricing",
    }
    return ctas.get(cat_key, BRAND["app_url"])


def _hashtags_for_category(cat_key: str) -> str:
    if cat_key in ("terrain",):
        return " ".join(HASHTAG_POOLS["terrain"][:4])
    if cat_key in ("yield", "economics"):
        return " ".join(HASHTAG_POOLS["yield"][:3] + ["#SolarDevelopment"])
    if cat_key == "founder":
        return " ".join(HASHTAG_POOLS["founder"][:4])
    return " ".join(HASHTAG_POOLS["general"][:4])


def build_100_ideas() -> list[dict]:
    ideas: list[dict] = []
    n = 1
    for cat_name, cat_key, count in CATEGORIES:
        seeds = IDEA_SEEDS.get(cat_key, [])
        for j in range(count):
            headline, hook, angle = seeds[j % len(seeds)]
            suffix = f" ({j + 1})" if j >= len(seeds) else ""
            full = (
                f"{hook}\n\n{angle}\n\n"
                f"{BRAND['name']} supports utility-scale ground-mount screening — "
                f"SiteIQ, TopoIQ, YieldIQ. Screening-grade; confirm before FEED.\n\n"
                f"{_cta_for_category(cat_key)}"
            )
            ideas.append({
                "id": n,
                "category": cat_name,
                "headline": f"{headline}{suffix}",
                "hook": hook,
                "full_post": full,
                "cta": _cta_for_category(cat_key),
                "hashtags": _hashtags_for_category(cat_key),
            })
            n += 1
    return ideas


def write_ideas_markdown(path: Path, ideas: list[dict]) -> None:
    lines = [
        "# PVMath — 100 LinkedIn post ideas",
        "",
        f"**Brand:** {BRAND['name']} — {BRAND['tagline']}",
        f"**Generated:** {date.today().isoformat()}",
        "",
        "Review and adapt before publishing. Do not auto-post.",
        "",
        "---",
        "",
    ]
    current_cat = ""
    for idea in ideas:
        if idea["category"] != current_cat:
            current_cat = idea["category"]
            lines.append(f"## {current_cat}")
            lines.append("")
        lines.append(f"### {idea['id']}. {idea['headline']}")
        lines.append("")
        lines.append(f"**Hook:** {idea['hook']}")
        lines.append("")
        lines.append("**Full post:**")
        lines.append("")
        for para in idea["full_post"].split("\n\n"):
            lines.append(para)
            lines.append("")
        lines.append(f"**CTA:** {idea['cta']}")
        lines.append("")
        lines.append(f"**Hashtags:** {idea['hashtags']}")
        lines.append("")
        lines.append("---")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def build_90_day_calendar(ideas: list[dict], start: date | None = None) -> list[dict]:
    """3 posts/week on Tue, Thu, Sat for 90 days."""
    start = start or date.today()
    end = start + timedelta(days=90)
    slots: list[date] = []
    d = start
    while d < end:
        if d.weekday() in (1, 3, 5):  # Tue, Thu, Sat
            slots.append(d)
        d += timedelta(days=1)

    rows = []
    for i, slot in enumerate(slots):
        idea = ideas[i % len(ideas)]
        rows.append({
            "publish_date": slot.isoformat(),
            "category": idea["category"],
            "headline": idea["headline"],
            "target_audience": AUDIENCES["epc"],
            "idea_id": idea["id"],
            "status": "planned",
            "draft_filename": "",
            "notes": "Generate fresh draft with pvmath_marketing_bot.py run",
        })
    return rows


def write_calendar_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    if not rows:
        return
    fieldnames = fieldnames or list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
