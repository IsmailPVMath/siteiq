"""30-minute TerrainIQ technical deep-dive — terrain screening + CAD export."""

from __future__ import annotations

from pvmath_deck.builder import DeckBuilder
from pvmath_deck.content import (
    ARCHITECTURE,
    DISCLAIMER,
    MODULES,
    PRICING,
    ROADMAP,
    TOPO_DEMO_STEPS,
    TOPO_QA,
)


def build_terrainiq_30(builder: DeckBuilder) -> None:
    """~18 slides · ~28 min talk + demo + Q&A."""

    builder.cover(
        title="TerrainIQ",
        subtitle="Terrain screening & CAD starter kit for ground-mount solar",
        notes=(
            "Technical audience: civil, layout, structural. "
            f"Open with scope: ground-mount only. {DISCLAIMER}"
        ),
        duration=45,
    )

    builder.agenda(
        [
            "Scope, data sources & honesty limits",
            "Inputs, outputs & engineering metrics",
            "Project Setup → boundary → analysis",
            "Live demo walkthrough",
            "Exports: PDF, LandXML, DXF",
            "Integration, limitations & Q&A",
        ],
        notes="30 minutes including ~8 min demo. Pause for questions on exports.",
        duration=30,
    )

    builder.bullets_slide(
        title="Who TerrainIQ is for",
        items=[
            "Civil / structural engineers evaluating buildability",
            "Layout engineers needing slope direction before row design",
            "EPC design teams reducing surprise topo costs",
            "Developers screening Agri-PV and tracker sites at scale",
            "Not for: rooftop, floating, or survey-grade as-built verification",
        ],
        notes="Ask room: fixed tilt, tracker, or mixed portfolio?",
        duration=60,
    )

    builder.bullets_slide(
        title="Purpose & scope",
        subtitle=MODULES["terrainiq"]["tagline"],
        items=[
            MODULES["terrainiq"]["purpose"],
            "Copernicus GLO-30 inside user-drawn or KMZ boundary",
            "Screening-grade — go/no-go and layout direction",
            "Complements SiteIQ (suitability) and YieldIQ (yield)",
            "Does not replace LiDAR, drone survey, or lender-grade topo",
        ],
        notes="Repeat Early Access disclaimer — reports state data limits.",
        duration=75,
        visual="Diagram: screening → survey → detailed design (placeholder)",
    )

    builder.bullets_slide(
        title="Data source — Copernicus GLO-30",
        items=[
            "Global DEM ~30 m native posting",
            "Resampled to analysis grid (default 5 m) for maps & contours",
            "Finer grid ≠ finer terrain detail — underlying limit ~30 m",
            "Consistent worldwide — no EU-only dataset switch in TerrainIQ",
            "Honest labeling on PDF exports",
        ],
        notes="Compare to LiDAR (cm–dm) and typical topo survey (decimetre).",
        duration=90,
        qa=[TOPO_QA[0], TOPO_QA[1]],
    )

    builder.table_slide(
        title="Inputs & outputs",
        headers=["Category", "Detail"],
        rows=[
            ("Inputs", MODULES["terrainiq"]["inputs"]),
            ("Outputs", MODULES["terrainiq"]["outputs"]),
            ("Typical runtime", MODULES["terrainiq"]["time"]),
            ("Users", MODULES["terrainiq"]["users"]),
        ],
        notes="Highlight LandXML + DXF as differentiator vs spreadsheet-only tools.",
        duration=75,
    )

    builder.bullets_slide(
        title="Engineering metrics",
        subtitle="Fixed tilt vs single-axis tracker thresholds",
        items=[
            "Fixed tilt: Excellent ≤5% · Acceptable ≤10% · Challenging ≤15%",
            "Tracker: Excellent ≤3% · Acceptable ≤6% · Challenging ≤10%",
            "Cross-row grade statistics (mean, p95) for tracker row spacing",
            "Verdict bands align with SiteIQ terrain flags",
            "Use for screening — detailed cut/fill comes after survey",
        ],
        notes="Explain why tracker limits are tighter than fixed.",
        duration=90,
        visual="Screenshot: cross-row grade panel",
    )

    for i, step in enumerate(TOPO_DEMO_STEPS):
        builder.bullets_slide(
            title=f"Demo — {step['title']}",
            items=step["bullets"],
            notes=step.get("talk", ""),
            duration=90 if i == 2 else 75,
            visual=step.get("visual", "Demo screenshot"),
            qa=[TOPO_QA[2]] if i == 3 else (),
        )

    builder.demo_steps(
        title="End-to-end demo flow",
        steps=TOPO_DEMO_STEPS,
        notes="Run live if possible; otherwise walk screenshots in order.",
        duration=120,
    )

    builder.bullets_slide(
        title="PDF terrain report",
        items=[
            "Project metadata + boundary summary",
            "Slope heatmap and statistics table",
            "Fixed / tracker verdict with threshold reference",
            "Data source and resampling disclaimer",
            "Same ReportLab styling as SiteIQ screening PDFs",
        ],
        notes="No emojis in PDF — professional engineering tone.",
        duration=60,
        visual="Screenshot: TerrainIQ PDF pages",
    )

    builder.bullets_slide(
        title="CAD exports",
        items=[
            "LandXML: UTM TIN surface for Civil 3D import",
            "DXF: contour lines + parcel/boundary linework",
            "Starter kit — add survey control and breaklines later",
            "Verify CRS on import; do not use for final grading bids alone",
            "CSV grid available for custom workflows",
        ],
        notes=TOPO_QA[2][1],
        duration=90,
        visual="Screenshot: Civil 3D import (placeholder)",
        qa=[TOPO_QA[2]],
    )

    builder.architecture(
        ARCHITECTURE,
        notes="Streamlit on Railway · Supabase auth · Copernicus + OpenTopoData where relevant.",
        duration=60,
    )

    builder.bullets_slide(
        title="Limitations — when to order survey",
        items=[
            "Steep or complex terrain — GLO-30 may under-resolve gullies",
            "Lender or EPC contract requires survey-grade surface",
            "Cut/fill quantities for BOQ — need measured topo",
            "Drainage and access road detail — beyond DEM screening",
            "TerrainIQ tells you whether survey spend is justified now",
        ],
        notes="Position TerrainIQ as filter before €10k–€50k+ survey spend.",
        duration=75,
    )

    builder.bullets_slide(
        title="Platform integration",
        items=[
            "Project Setup (Full Mode) — boundary shared with SiteIQ context",
            "SiteIQ land use + mounting informs density and verdict language",
            "YieldIQ uses same location for configuration compare",
            "Agri-PV: lower MW/ha in SiteIQ; terrain limits unchanged",
            "Developer tier: pooled analyses for high-volume screening",
        ],
        notes=TOPO_QA[3][1],
        duration=60,
        qa=[TOPO_QA[3]],
    )

    builder.roadmap(
        ROADMAP,
        notes="LayoutIQ will consume TerrainIQ surfaces for auto row layout — future.",
        duration=45,
    )

    builder.pricing(
        notes="Free tier: 5 TerrainIQ runs/month separate cap. Pooled on Pro/Developer.",
        duration=45,
    )

    builder.bullets_slide(
        title="Anticipated Q&A",
        items=[f"Q: {q}\nA: {a}" for q, a in TOPO_QA],
        notes="Use as backup slide if live Q&A is quiet.",
        duration=60,
    )

    builder.qa_contact(
        notes="Offer pilot: 5 boundaries from their pipeline. Send sample LandXML/DXF after.",
        duration=60,
    )

    builder.speaker_script_appendix(
        {
            "Opening": "TerrainIQ technical session — terrain screening with CAD handoff.",
            "Data honesty": "GLO-30 ~30 m native; 5 m grid for workflow only.",
            "Demo script": "\n".join(
                f"Step {i+1} — {s['title']}: {s.get('talk', '')}"
                for i, s in enumerate(TOPO_DEMO_STEPS)
            ),
            "Close": f"{PRICING} · contact@pvmath.com",
        }
    )
