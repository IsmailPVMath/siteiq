# PVMath Marketing

LinkedIn draft generation and content library. **No auto-posting.**

## Quick start

```bash
# One-time: 100 ideas, 90-day strategy, publishing calendar, templates
python3 scripts/pvmath_marketing_bot.py init-library

# Weekly: 5 fresh LinkedIn drafts + CSV row
python3 scripts/pvmath_marketing_bot.py run
```

## Structure

| Path | Purpose |
|------|---------|
| `linkedin_drafts/` | Bot output — review before publishing (gitignored `.md`) |
| `content_strategy/` | 90-day strategy, 100 ideas, publishing calendar |
| `linkedin_posts/` | Seed and curated full posts |
| `post_templates/` | Reusable post formats |
| `content_calendar.csv` | Run log: topic, title, audience, draft filename |

## Rules

- Screening-grade disclaimers on yield and terrain
- No cut/fill or bankability overclaims
- Ground-mount utility-scale only
- Founder-led, technical tone — no hype
