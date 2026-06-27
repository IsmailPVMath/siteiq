"""15-minute EPC / developer sales deck — SiteIQ + TerrainIQ + YieldIQ."""

from __future__ import annotations

from pvmath_deck.builder import DeckBuilder
from pvmath_deck.content import (
    ARCHITECTURE,
    BENEFITS,
    DISCLAIMER,
    MANUAL_WORKFLOW,
    MODULES,
    PRICING,
    PROBLEMS,
    PVMATH_WORKFLOW,
    ROADMAP,
    SALES_DEMO_STEPS,
)


def build_sales_15(builder: DeckBuilder) -> None:
    """~15 slides · ~14 min talk + 1 min buffer."""

    builder.cover(
        title="Ground-mount site intelligence",
        subtitle="Screen faster. Advance fewer dead-end sites.",
        notes=(
            "Introduce yourself and the customer context (pipeline stage, geography, "
            "fixed vs tracker mix). State ground-mount only — no rooftop. "
            f"Repeat disclaimer: {DISCLAIMER}"
        ),
        duration=45,
    )

    builder.agenda(
        [
            "Why screening breaks down today",
            "PVMath workflow — one project, three modules",
            "SiteIQ · TerrainIQ · YieldIQ overview",
            "Live demo flow",
            "Pricing & next steps",
        ],
        notes="Set expectation: 15 minutes, Q&A at end. Offer to go deeper on TerrainIQ in a follow-up.",
        duration=30,
    )

    builder.bullets_slide(
        title="The problem",
        subtitle="Ground-mount pipelines lose time on sites that should fail early",
        items=PROBLEMS,
        notes=(
            "Ask: how many sites did your team advance last quarter before terrain or "
            "yield killed them? Do not invent customer stats — use their answer."
        ),
        duration=75,
        visual="Photo: empty field / early-stage site (placeholder)",
    )

    builder.two_column(
        title="Manual screening vs PVMath",
        left_title="Typical manual workflow",
        left_items=MANUAL_WORKFLOW,
        right_title="PVMath workflow",
        right_items=PVMATH_WORKFLOW,
        notes=(
            "Position as workflow compression, not a magic accuracy upgrade. "
            "Screening-grade outputs with honest disclaimers."
        ),
        duration=90,
    )

    builder.bullets_slide(
        title="What is PVMath?",
        subtitle="Solar Site Intelligence Platform — ground mount only",
        items=[
            "SiteIQ — rapid suitability screening (solar, terrain flag, flood, regulatory hints)",
            "TerrainIQ — Copernicus terrain screening + CAD starter exports",
            "YieldIQ — four-configuration yield comparison before PVsyst",
            "One project setup shared across modules",
            "Early Access — contact@pvmath.com for team activation",
        ],
        notes="Tagline: From site to system. Live at siteiq.pvmath.com.",
        duration=60,
        visual="Screenshot: app sidebar with three modules",
    )

    builder.module_card_slide(
        title="Three modules — one platform",
        modules=[MODULES["siteiq"], MODULES["terrainiq"], MODULES["yieldiq"]],
        notes=(
            "Walk left to right. Emphasise time-to-output, not precision claims. "
            "SiteIQ ≤4 min · TerrainIQ ~20–60 s · YieldIQ ≤4 min (typical)."
        ),
        duration=90,
    )

    m = MODULES["siteiq"]
    builder.bullets_slide(
        title="SiteIQ — first gate",
        subtitle=m["tagline"],
        items=[
            f"Inputs: {m['inputs']}",
            f"Outputs: {m['outputs']}",
            f"Data: {m['data']}",
            "Standard vs Agri-PV density · Fixed tilt vs single-axis tracker",
            "Screening PDF for gate meetings",
        ],
        notes="Offer sample PDF from pvmath.com if offline.",
        duration=60,
        visual="Screenshot: SiteIQ suitability + PDF download",
    )

    m = MODULES["terrainiq"]
    builder.bullets_slide(
        title="TerrainIQ — terrain before survey",
        subtitle=m["tagline"],
        items=[
            f"Inputs: {m['inputs']}",
            f"Outputs: {m['outputs']}",
            "Tracker cross-row grade metrics — not just mean slope",
            "LandXML + DXF for civil workflow starter kit",
            f"Data: {m['data']}",
        ],
        notes="Tease deeper TerrainIQ session for civil leads.",
        duration=60,
        visual="Screenshot: TerrainIQ slope heatmap",
    )

    m = MODULES["yieldiq"]
    builder.bullets_slide(
        title="YieldIQ — configuration compare",
        subtitle=m["tagline"],
        items=[
            f"Inputs: {m['inputs']}",
            f"Outputs: {m['outputs']}",
            "Compare SAT vs fixed · 1P vs 2P in one run",
            "Not bankable yield — directionally correct for feasibility",
            f"Data: {m['data']}",
        ],
        notes="Stress not bankable — use for configuration direction before PVsyst.",
        duration=60,
        visual="Screenshot: YieldIQ comparison chart",
    )

    builder.demo_steps(
        title="Live demo — suggested flow",
        steps=SALES_DEMO_STEPS,
        notes=(
            "Pick ONE site the customer knows. SiteIQ first (Quick Mode), then Full Mode "
            "boundary if time allows. Skip YieldIQ if clock is tight."
        ),
        duration=180,
    )

    builder.bullets_slide(
        title="Why teams use PVMath",
        items=BENEFITS,
        notes="Tie each bullet to customer pain from slide 3.",
        duration=60,
    )

    builder.architecture(
        ARCHITECTURE,
        notes="Only if technical buyer present — otherwise skip verbally.",
        duration=45,
    )

    builder.pricing(
        notes=f"Read tiers from slide. Full text: {PRICING}. Stripe not live — email for activation.",
        duration=45,
    )

    builder.roadmap(
        ROADMAP,
        notes="RevenueIQ + LayoutIQ next — do not over-promise dates.",
        duration=45,
    )

    builder.qa_contact(
        notes=(
            "Close with concrete next step: free account, pilot on 3 sites, or TerrainIQ deep-dive. "
            "Collect follow-up contact."
        ),
        duration=60,
    )

    builder.speaker_script_appendix(
        {
            "Opening": "Thank [customer]. Today: how PVMath compresses ground-mount screening.",
            "Demo": "\n".join(
                f"{s['title']}: " + "; ".join(s["bullets"]) for s in SALES_DEMO_STEPS
            ),
            "Close": f"Try free at siteiq.pvmath.com · {PRICING}",
        }
    )
