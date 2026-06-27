#!/usr/bin/env python3
"""
PVMath Content Bot — weekly marketing assignment generator.

Usage:
    python3 scripts/pvmath_content_bot.py
    python3 scripts/pvmath_content_bot.py --email
    python3 scripts/pvmath_content_bot.py --week 3

Writes marketing/drafts/YYYY-MM-DD-weekly-assignment.md with calendar slot
and a ready-to-paste Cursor agent prompt.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "marketing" / "drafts"

CALENDAR = [
    {
        "pillar": "Workflow",
        "tue": "One Project Setup → SiteIQ, TerrainIQ, YieldIQ on the same boundary",
        "thu": "Screening vs survey — what you can decide in week one",
        "guide": "screening-vs-survey",
    },
    {
        "pillar": "Terrain before LiDAR",
        "tue": "KMZ arrives Monday — LandXML/DXF screening package same day",
        "thu": "TerrainIQ before you commit LiDAR budget on every greenfield site",
        "guide": "landxml-dxf-solar",
    },
    {
        "pillar": "Honest DEM",
        "tue": "Copernicus GLO-30 is ~30 m native — we say it on every report",
        "thu": "5 m output grid is for layout/CAD — not new sensor resolution",
        "guide": "glo30-and-5m-grid",
    },
    {
        "pillar": "Tracker cross-row",
        "tue": "Mean slope can look excellent on rolling tracker sites",
        "thu": "Cross-row grade drives clearance — check p95 not just average",
        "guide": "mean-slope-vs-cross-row",
    },
    {
        "pillar": "CAD handoff",
        "tue": "Parcel linework on SITE_BOUNDARY in DXF and LandXML",
        "thu": "US projects: georef exports in US Survey Feet — no extra scaling",
        "guide": "landxml-dxf-solar",
    },
    {
        "pillar": "SiteIQ screening",
        "tue": "Portfolio go/no-go PDF without pretending bankability",
        "thu": "Flood indicator is a checklist flag — not official mapping",
        "guide": "siteiq-screening",
    },
    {
        "pillar": "YieldIQ configuration",
        "tue": "Compare SAT vs fixed tilt at the same GCR before PVsyst",
        "thu": "Specific yield, PR, CF — configuration choice in pre-feasibility",
        "guide": "yieldiq-yield",
    },
    {
        "pillar": "Screening vs survey",
        "tue": "When LiDAR earns its budget on a shortlisted site",
        "thu": "What screening cannot replace (FEED, stamped civil, lender yield)",
        "guide": "screening-vs-survey",
    },
    {
        "pillar": "Regional DE",
        "tue": "DACH greenfield workflow — screening PDF for internal gate",
        "thu": "Regulatory pointers in SiteIQ — not legal advice",
        "guide": "siteiq-screening",
    },
    {
        "pillar": "Regional ES/IN",
        "tue": "High irradiance sites still need terrain and CAD handoff",
        "thu": "YieldIQ four configs — tracker gain conversation early",
        "guide": "yieldiq-yield",
    },
    {
        "pillar": "Case study style",
        "tue": "Anonymised: KMZ → TerrainIQ → LiDAR scoped to 40 ha problem area",
        "thu": "Anonymised: YieldIQ chose SAT 1P over fixed at screening GCR",
        "guide": "terrainiq-metrics",
    },
    {
        "pillar": "Platform",
        "tue": "From site to system — one platform, three live modules",
        "thu": "Knowledge Centre for engineers + Pro manual for customers",
        "guide": "index",
    },
]

MARKETS = ["Germany (DE)", "Spain (ES)", "India (IN)", "GCC / US"]


def iso_week_index(d: date | None = None) -> int:
    d = d or date.today()
    return d.isocalendar().week % 12


def market_for_week(week_idx: int) -> str:
    return MARKETS[week_idx % 4]


def build_assignment(week_idx: int, *, include_email: bool) -> str:
    slot = CALENDAR[week_idx]
    market = market_for_week(week_idx)
    guide_url = f"https://pvmath.com/guides/{slot['guide']}.html"
    today = date.today().isoformat()

    email_block = ""
    if include_email or (week_idx % 2 == 1):
        email_block = f"""
## Thursday bonus — EPC email (optional)

Generate Format 6 (outbound email) for civil/EPC lead in **{market}**.
Topic: {slot['thu']}
Soft CTA: 15-min call or free trial at siteiq.pvmath.com
"""

    return f"""# PVMath weekly content assignment
**Generated:** {today}  
**Calendar week index:** {week_idx} / 12  
**Pillar:** {slot['pillar']}  
**Example market:** {market}  
**Guide CTA:** {guide_url}

---

## Tuesday LinkedIn

**Brief:** {slot['tue']}

- Audience: EPC / project developer / civil engineer  
- Module focus: infer from brief (SiteIQ / TerrainIQ / YieldIQ / platform)  
- CTA: Knowledge Centre link above OR siteiq.pvmath.com  
- Include screening-grade disclaimer if discussing outputs  

Deliver: **main + Variation A (short) + Variation B (technical)**

---

## Thursday LinkedIn

**Brief:** {slot['thu']}

Same rules as Tuesday. Different angle — do not repeat Tuesday hook.
{email_block}
---

## Agent prompt (paste into Cursor)

```
You are the PVMath Marketing Content Assistant.

Read these files from the repo:
- .cursor/skills/pvmath-marketing/SKILL.md
- .cursor/skills/pvmath-marketing/templates.md
- .cursor/skills/pvmath-marketing/examples.md

Execute this week's assignment from marketing/drafts/{today}-weekly-assignment.md.

Rules:
- European engineering tone, no hype words
- Never publish proprietary score weights or thresholds
- Ground-mount only (fixed tilt, tracker, Agri-PV)
- Example market: {market}

Output Tuesday and Thursday LinkedIn posts.
Each post: MAIN + Variation A (shorter) + Variation B (more technical).

Append results under ## Generated Content below.
```

---

## Generated Content

*(Agent fills this section)*

---

## Approved for publish

*(Paste winning versions after your review)*

- **Tue date published:**  
- **Thu date published:**  
"""


def main():
    parser = argparse.ArgumentParser(description="PVMath weekly content bot")
    parser.add_argument("--week", type=int, help="Force calendar week index 0–11")
    parser.add_argument("--email", action="store_true", help="Include Thursday email block")
    parser.add_argument("--stdout", action="store_true", help="Print only, do not write file")
    args = parser.parse_args()

    week_idx = args.week if args.week is not None else iso_week_index()
    if not 0 <= week_idx <= 11:
        raise SystemExit("Week index must be 0–11")

    body = build_assignment(week_idx, include_email=args.email)
    out_name = f"{date.today().isoformat()}-weekly-assignment.md"

    if args.stdout:
        print(body)
        return

    DRAFTS.mkdir(parents=True, exist_ok=True)
    out_path = DRAFTS / out_name
    out_path.write_text(body, encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"Week slot {week_idx}: {CALENDAR[week_idx]['pillar']}")
    print(f"Market: {market_for_week(week_idx)}")
    print("\nNext: open the file and paste the Agent prompt into Cursor chat.")


if __name__ == "__main__":
    main()
