"""Generate LinkedIn post draft bodies — professional, no hype."""

from __future__ import annotations

from datetime import date

from pvmath_marketing.brand import BRAND, DISCLAIMER_SCREENING, TOPICS_RUN


def _hashtag_line(tags: list[str]) -> str:
    return " ".join(tags[:5])


def draft_siteiq(variant: int = 0) -> dict[str, str]:
    hooks = [
        "Your land team sends coordinates on Tuesday. Engineering wants a go/no-go by Friday.",
        "Portfolio screening is not one spreadsheet — it is solar, terrain, flood flags, and capacity in one pass.",
        "Investors ask for a number. Engineers ask if the site is buildable. Both need the same screening PDF.",
    ]
    bodies = [
        f"""Most early-stage failures are visible before LiDAR — if you screen consistently.

**SiteIQ** combines PVGIS solar resource, terrain sampling (or TopoIQ-confirmed GLO-30), flood heuristics, and country-aware regulatory pointers into one screening report and PDF.

Use the **PVMath Score** for portfolio ranking — a deterministic screening index, not a bankability rating.

{DISCLAIMER_SCREENING}

Try free: {BRAND['app_url']} · Guides: {BRAND['guides']}""",
        f"""One **Project Setup** — name, country, boundary or pin — then **SiteIQ** for combined screening.

Fixed tilt, tracker, Standard or Agri-PV density bands. PDF ready for internal gate reviews.

Built by a solar engineer who got tired of rebuilding the same pre-feasibility pack.

{BRAND['name']} — {BRAND['tagline']}""",
    ]
    insights = [
        "Indicative DC capacity uses industry-typical MWp/ha bands — layout-optimised designs will differ.",
        "Flood flags are checklist items — not official hydrology or FEMA mapping.",
    ]
    i = variant % len(hooks)
    return {
        "hook": hooks[i],
        "body": bodies[i % len(bodies)],
        "insight": insights[i % len(insights)],
        "soft_mention": f"{BRAND['name']} SiteIQ — screening before survey spend.",
    }


def draft_topoiq(variant: int = 0) -> dict[str, str]:
    hooks = [
        "LiDAR is the right answer — but not on every site on day one.",
        "Civil asked for contours and parcel linework. The KMZ only had a boundary.",
        "Mean slope looked fine. Cross-row grade told a different story for trackers.",
    ]
    bodies = [
        f"""**TopoIQ** turns your site boundary into screening-grade terrain: Copernicus GLO-30, **5 m layout grid** (native DEM ~30 m — we disclose both), slope maps, cross-row statistics for single-axis trackers, and engineering verdicts.

Export **LandXML**, georef **DXF** with **SITE_BOUNDARY** linework, and a terrain PDF — UTM + US Survey Feet for US projects.

Not pile schedules or cut/fill quantities — early constructability and CAD starter geometry.

{DISCLAIMER_SCREENING}

{BRAND['app_url']}""",
        f"""Before you order topo survey, ask: does mean slope hide rolling terrain?

TopoIQ reports mean and max slope plus **cross-row** metrics for tracker screening — where clearance and grading conversations start.

{BRAND['name']} TopoIQ — terrain before LiDAR.""",
    ]
    insights = [
        "Contour DXF lines are clipped to the site polygon — no rectangular grid artifacts in CAD.",
        "Multi-parcel KMZ: merged surface; gaps may show as TIN seams — use one continuous boundary when possible.",
    ]
    i = variant % len(hooks)
    return {
        "hook": hooks[i],
        "body": bodies[i % len(bodies)],
        "insight": insights[i % len(insights)],
        "soft_mention": f"{BRAND['name']} TopoIQ — from KMZ to CAD-ready screening outputs.",
    }


def draft_yieldiq(variant: int = 0) -> dict[str, str]:
    hooks = [
        "Fixed tilt or tracker — the wrong default at screening stage costs months.",
        "PVsyst is the right tool later. Before that, you need a fair configuration comparison.",
        "GCR changes both DC density and row shading — compare configs at the same geometry.",
    ]
    bodies = [
        f"""**YieldIQ** runs **PVGIS** for four ground-mount configurations: 1P/2P fixed tilt and 1P/2P single-axis tracker at your GCR and loss assumptions.

Outputs: specific yield (kWh/kWp/yr), PR, capacity factor, POA irradiance, shading and total loss breakdown.

Typically ±8–15% vs bankable studies — suitable for **configuration choice**, not lender sign-off.

{DISCLAIMER_SCREENING}

{BRAND['app_url']}""",
        f"""Compare tracker gain vs fixed at the **same GCR** before you open detailed modelling.

YieldIQ uses disclosed screening assumptions — temperature from PVGIS physics, not a flat guess.

{BRAND['name']} YieldIQ — preliminary yield, honest limits.""",
    ]
    insights = [
        "SiteIQ uses a lighter screening profile; YieldIQ uses a richer analysis profile — same location, different depth.",
        "Capacity screening MWp/ha uses a standard GCR band — separate from YieldIQ GCR sliders.",
    ]
    i = variant % len(hooks)
    return {
        "hook": hooks[i],
        "body": bodies[i % len(bodies)],
        "insight": insights[i % len(insights)],
        "soft_mention": f"{BRAND['name']} YieldIQ — four configs, one coordinate pair.",
    }


def draft_utility_problems(variant: int = 0) -> dict[str, str]:
    hooks = [
        "Utility-scale development loses weeks at the handoff between land, GIS, and engineering.",
        "The expensive mistake is not bad solar resource — it is bad terrain discovered after option payment.",
        "Every greenfield site pays for the same manual steps until someone standardises screening.",
    ]
    bodies = [
        f"""Common early-stage friction:

→ KMZ arrives without a screening pack civil can use  
→ Mean slope quoted without tracker cross-row context  
→ Yield compared across inconsistent GCR assumptions  
→ LiDAR ordered before the site earns it  

**PVMath** packages one project setup into **SiteIQ**, **TopoIQ**, and **YieldIQ** — screening-grade, engineer-written outputs.

{BRAND['tagline']} · {BRAND['website']}""",
        f"""Land acquisition optimises for hectares. Engineering optimises for constructability. Finance optimises for speed.

Without a shared screening layer, each team rebuilds the same analysis in Excel.

We built {BRAND['name']} for that gap — ground-mount only, global datasets, honest disclaimers.""",
    ]
    insights = [
        "Order LiDAR when terrain and resource justify spend — not by default on every pin.",
        "Agri-PV screening uses lower MWp/ha bands — land use choice affects both capacity and permitting path.",
    ]
    i = variant % len(hooks)
    return {
        "hook": hooks[i],
        "body": bodies[i % len(bodies)],
        "insight": insights[i % len(insights)],
        "soft_mention": f"{BRAND['name']} — practical screening for utility-scale teams.",
    }


def draft_founder(variant: int = 0) -> dict[str, str]:
    hooks = [
        "Building PVMath alongside a full-time solar engineering job — weeknights and honest scope.",
        "Every feature in SiteIQ, TopoIQ, and YieldIQ exists because a real screening step was painful.",
        "Shipping screening-grade outputs, not black-box scores — that was the product decision.",
    ]
    bodies = [
        f"""I'm {BRAND['founder']} — solar engineer, building **{BRAND['name']}** as a side project while working in utility-scale PV.

Live today: **SiteIQ** (combined screening), **TopoIQ** (terrain + CAD exports), **YieldIQ** (configuration yield). One Project Setup, three modules.

Recent focus: contour clipping for clean Civil 3D imports, Knowledge Centre for public engineering guides, Pro-tier customer manual — no proprietary formulas published.

{DISCLAIMER_SCREENING}

Follow the build: {BRAND['website']} · Try: {BRAND['app_url']}""",
        f"""Why {BRAND['name']}?

I kept rebuilding the same pre-feasibility workflow — coordinates in, PDF and CAD out, disclaimers included.

Ground-mount only. Fixed tilt, tracker, Agri-PV. Global PVGIS + GLO-30. Not rooftop, not hype.

If you screen utility-scale sites, I'd value your feedback on what we ship next.""",
    ]
    insights = [
        "Railway-hosted app, Supabase auth, Copernicus + PVGIS — frugal stack, professional outputs.",
        "Roadmap includes revenue and layout modules — shipping when they meet the same screening honesty bar.",
    ]
    i = variant % len(hooks)
    return {
        "hook": hooks[i],
        "body": bodies[i % len(bodies)],
        "insight": insights[i % len(insights)],
        "soft_mention": f"{BRAND['name']} — built by a solar engineer, for solar engineers.",
    }


GENERATORS = {
    "siteiq-solar-site-screening": draft_siteiq,
    "topoiq-terrain-slope-analysis": draft_topoiq,
    "yieldiq-preliminary-yield": draft_yieldiq,
    "utility-scale-development-problems": draft_utility_problems,
    "founder-build-in-public": draft_founder,
}


def render_draft_markdown(
    topic_meta: dict,
    content: dict[str, str],
    hashtags: list[str],
    run_date: date | None = None,
) -> str:
    run_date = run_date or date.today()
    return f"""---
title: {topic_meta['title']}
module: {topic_meta['module']}
category: {topic_meta['category']}
audience: {topic_meta.get('audience_key', topic_meta['audience'])}
date: {run_date.isoformat()}
status: draft
auto_post: false
---

# {topic_meta['title']}

## Hook
{content['hook']}

## Body
{content['body']}

## Practical insight
{content['insight']}

## Soft mention
{content['soft_mention']}

## Hashtags
{_hashtag_line(hashtags)}

---
*Review before publishing. Do not auto-post. {BRAND['name']} Marketing Bot.*
"""
