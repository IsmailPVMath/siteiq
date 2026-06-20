"""PVMath Marketing Bot — orchestration."""

from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

from pvmath_marketing.brand import AUDIENCES, BRAND, TOPICS_RUN
from pvmath_marketing.drafts import GENERATORS, render_draft_markdown
from pvmath_marketing.ideas import (
    build_100_ideas,
    build_90_day_calendar,
    write_calendar_csv,
    write_ideas_markdown,
)

ROOT = Path(__file__).resolve().parents[1]
MARKETING = ROOT / "marketing"
DRAFTS_DIR = MARKETING / "linkedin_drafts"
STRATEGY_DIR = MARKETING / "content_strategy"
POSTS_DIR = MARKETING / "linkedin_posts"
TEMPLATES_DIR = MARKETING / "post_templates"
RUN_CALENDAR_CSV = MARKETING / "content_calendar.csv"


def ensure_dirs() -> None:
    for d in (DRAFTS_DIR, STRATEGY_DIR, POSTS_DIR, TEMPLATES_DIR):
        d.mkdir(parents=True, exist_ok=True)


def run_drafts(run_date: date | None = None) -> list[Path]:
    """Generate 5 LinkedIn draft .md files + append to content_calendar.csv."""
    ensure_dirs()
    run_date = run_date or date.today()
    variant = run_date.toordinal() % 3
    written: list[Path] = []
    calendar_rows: list[dict] = []

    for topic in TOPICS_RUN:
        gen = GENERATORS[topic["slug"]]
        content = gen(variant)
        audience_key = topic["audience"]
        meta = {**topic, "audience_key": audience_key}
        md = render_draft_markdown(meta, content, topic["hashtags"], run_date)
        filename = f"{run_date.isoformat()}-{topic['slug']}.md"
        path = DRAFTS_DIR / filename
        path.write_text(md, encoding="utf-8")
        written.append(path)

        calendar_rows.append({
            "run_date": run_date.isoformat(),
            "topic": topic["slug"],
            "title": topic["title"],
            "target_audience": AUDIENCES.get(audience_key, audience_key),
            "category": topic["category"],
            "draft_filename": f"linkedin_drafts/{filename}",
            "status": "draft",
        })

    _append_run_calendar(calendar_rows)
    return written


def _append_run_calendar(rows: list[dict]) -> None:
    fieldnames = [
        "run_date", "topic", "title", "target_audience",
        "category", "draft_filename", "status",
    ]
    exists = RUN_CALENDAR_CSV.exists()
    with RUN_CALENDAR_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            w.writeheader()
        w.writerows(rows)


def init_library(start: date | None = None) -> dict[str, Path]:
    """Build 90-day strategy assets, 100 ideas, publishing calendar, templates."""
    ensure_dirs()
    start = start or date.today()
    ideas = build_100_ideas()
    outputs: dict[str, Path] = {}

    ideas_md = STRATEGY_DIR / "100-post-ideas.md"
    write_ideas_markdown(ideas_md, ideas)
    outputs["ideas"] = ideas_md

    cal_rows = build_90_day_calendar(ideas, start)
    cal_csv = STRATEGY_DIR / "publishing-calendar-90d.csv"
    write_calendar_csv(cal_csv, cal_rows)
    outputs["calendar"] = cal_csv

    strategy_md = STRATEGY_DIR / "90-day-linkedin-strategy.md"
    if not strategy_md.exists():
        strategy_md.write_text(_strategy_template(start), encoding="utf-8")
    outputs["strategy"] = strategy_md

    _write_templates()
    outputs["templates"] = TEMPLATES_DIR

    for i, idea in enumerate(ideas[:5], start=1):
        slug = idea["category"][:12].lower().replace(" ", "-")
        p = POSTS_DIR / f"seed-{i:03d}-{slug}.md"
        p.write_text(_idea_to_post_md(idea), encoding="utf-8")

    return outputs


def _idea_to_post_md(idea: dict) -> str:
    return f"""---
id: {idea['id']}
category: {idea['category']}
status: seed
---

# {idea['headline']}

{idea['hook']}

{idea['full_post']}

**Hashtags:** {idea['hashtags']}
"""


def _strategy_template(start: date) -> str:
    end = start + timedelta(days=90)
    return f"""# PVMath 90-day LinkedIn strategy

**Period:** {start.isoformat()} → {end.isoformat()}  
**Cadence:** 3 posts/week (Tuesday, Thursday, Saturday)  
**Owner:** {BRAND['founder']} / PVMath  
**Auto-post:** No — all drafts reviewed manually

## Objective

Build technical trust with utility-scale EPCs, developers, and civil teams in DE · ES · IN · GCC. Drive free trials and Pro upgrades without hype or false precision claims.

## Positioning

**PVMath** — Solar Site Intelligence Platform. **From site to system.**

Live modules: SiteIQ (screening), TopoIQ (terrain + CAD), YieldIQ (configuration yield). Ground-mount only. Screening-grade outputs with explicit limits.

## Content mix (weekly)

| Slot | Typical focus |
|------|----------------|
| Tue | Educational or terrain/yield deep dive |
| Thu | Product workflow or customer pain point |
| Sat | Founder journey or industry commentary |

## Channels

- **LinkedIn** (primary) — founder profile + company page
- **Knowledge Centre** — CTA in 40%+ of posts
- **Website** — pricing and module proof

## KPIs (track monthly)

- LinkedIn impressions and profile visits
- siteiq.pvmath.com signups (UTM: linkedin)
- Inbound contact@ mentioning screening / CAD
- Free → Professional conversion

## Bot workflow

```bash
python3 scripts/pvmath_marketing_bot.py run          # 5 fresh drafts
python3 scripts/pvmath_marketing_bot.py init-library # one-time 100 ideas + 90d calendar
```

## Rules

- No cut/fill or bankability claims unless product supports them
- Always disclose GLO-30 ~30 m native vs 5 m grid when discussing TopoIQ
- Never publish proprietary score weights
- Ground-mount scope only

## Related files

- `100-post-ideas.md` — full idea library
- `publishing-calendar-90d.csv` — dated plan
- `../post_templates/` — reusable formats
- `../linkedin_drafts/` — bot output per run
"""


def _write_templates() -> None:
    templates = {
        "feature-announcement.md": _tpl_feature(),
        "industry-commentary.md": _tpl_industry(),
        "founder-update.md": _tpl_founder(),
        "product-milestone.md": _tpl_milestone(),
        "customer-success-story.md": _tpl_customer(),
    }
    for name, body in templates.items():
        path = TEMPLATES_DIR / name
        if not path.exists():
            path.write_text(body, encoding="utf-8")


def _tpl_feature() -> str:
    return """# Template: Feature announcement

**Hook:** [One engineering pain this feature removes]

**Body:**
- What shipped: [Module — feature name]
- Who it helps: [EPC / civil / developer]
- How it works: [1–2 sentences, public-safe]
- Limitation: [Screening-grade disclaimer if applicable]

**Soft mention:** PVMath [Module] — [one-line value]

**CTA:** Try free at siteiq.pvmath.com · Guide: pvmath.com/guides/

**Hashtags:** #GroundMountSolar #UtilityScale #SolarEPC #SolarDevelopment
"""


def _tpl_industry() -> str:
    return """# Template: Industry commentary

**Hook:** [Observation about utility-scale market — DE/ES/IN/GCC]

**Body:**
- Context: [pipeline speed, terrain, tariffs, supply chain]
- Engineering angle: [what teams get wrong at screening stage]
- Practical takeaway: [actionable without selling]

**Soft mention:** We see this building PVMath for ground-mount screening.

**CTA:** How does your team handle this? Comment or DM.

**Hashtags:** #SolarDevelopment #RenewableEnergy #UtilityScale
"""


def _tpl_founder() -> str:
    return """# Template: Founder update

**Hook:** [Honest build-in-public line — weeknight shipping, user feedback, etc.]

**Body:**
- Shipped: [specific, verifiable]
- Learned: [from user or code]
- Next: [roadmap item with honesty bar]

**Soft mention:** PVMath — built by a solar engineer, for solar engineers.

**CTA:** pvmath.com · Feedback welcome from EPC teams.

**Hashtags:** #BuildInPublic #SolarEngineering #CleanTech
"""


def _tpl_milestone() -> str:
    return """# Template: Product milestone

**Hook:** [Milestone — users, exports, guides, module live]

**Body:**
- What changed for users: [concrete]
- Why it matters: [time saved / risk reduced]
- What it is not: [no overclaim]

**CTA:** siteiq.pvmath.com

**Hashtags:** #GroundMountSolar #SolarEPC #SiteIQ #TopoIQ #YieldIQ
"""


def _tpl_customer() -> str:
    return """# Template: Customer success story (anonymised)

**Hook:** [Problem before screening — no client names unless approved]

**Context:** [Region · ~MWp · mount type · land use]

**Approach:** [SiteIQ / TopoIQ / YieldIQ — what was run]

**Outcome:** [Time saved, decision made, LiDAR scoped/deferred — real numbers only if provided]

**Engineer note:** Screening-grade — confirm with survey before FEED.

**CTA:** Run your anonymised site: siteiq.pvmath.com

**Hashtags:** #UtilityScale #SolarEPC #GroundMountSolar
"""
