# PVMath 90-day LinkedIn strategy

**Period:** 2026-06-21 → 2026-09-19  
**Cadence:** 3 posts/week (Tuesday, Thursday, Saturday)  
**Owner:** Ismail Pasha / PVMath  
**Auto-post:** No — all drafts reviewed manually

## Objective

Build technical trust with utility-scale EPCs, developers, and civil teams in DE · ES · IN · GCC. Drive free trials and Pro upgrades without hype or false precision claims.

## Positioning

**PVMath** — Solar Site Intelligence Platform. **From site to system.**

Live modules: SiteIQ (screening), TerrainIQ (terrain + CAD), YieldIQ (configuration yield). Ground-mount only. Screening-grade outputs with explicit limits.

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
- Always disclose GLO-30 ~30 m native vs 5 m grid when discussing TerrainIQ
- Never publish proprietary score weights
- Ground-mount scope only

## Related files

- `100-post-ideas.md` — full idea library
- `publishing-calendar-90d.csv` — dated plan
- `../post_templates/` — reusable formats
- `../linkedin_drafts/` — bot output per run
