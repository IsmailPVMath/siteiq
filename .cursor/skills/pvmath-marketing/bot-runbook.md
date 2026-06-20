# PVMath Content Bot — runbook

The **PVMath Content Bot** is not a separate app. It is:

1. **`scripts/pvmath_content_bot.py`** — picks this week’s topics from the calendar  
2. **`.cursor/skills/pvmath-marketing/`** — brand rules + templates  
3. **You (or Cursor Agent)** — generates 3 variants per post, you approve & publish  
4. **Optional: Cursor Automation** — runs the agent prompt on a schedule  

---

## Quick start (every Monday, ~5 min)

```bash
cd ~/Desktop/solarscout
python3 scripts/pvmath_content_bot.py
```

Open the generated file in `marketing/drafts/` and paste the **Agent prompt** block into Cursor chat (Agents window).

The agent returns:
- Tue LinkedIn: main + 2 variations  
- Thu LinkedIn: main + 2 variations  
- (Optional) Thu email snippet on odd weeks  

**You publish** to LinkedIn manually (or Buffer/Later). Bot does not auto-post — keeps brand control.

---

## Agent invocation (copy-paste)

```
Read .cursor/skills/pvmath-marketing/SKILL.md and execute the weekly assignment
in marketing/drafts/<latest-file>.md

Deliver all required formats with main + 2 variations each.
Save final approved copy back into the same draft file under ## Approved.
```

---

## Cursor Automation (recommended — 2× weekly)

**Trigger:** Schedule — Tue & Thu 07:00 UTC (08:00 CET)  
**Repo:** IsmailPVMath/siteiq · branch `main`  
**Agent job:**

1. Run `python3 scripts/pvmath_content_bot.py`  
2. Read the new draft file + pvmath-marketing skill  
3. Generate Tue OR Thu content based on day (Tue = first post, Thu = second)  
4. Write output to `marketing/drafts/` with date stamp  
5. Do **not** publish externally — draft only  

**You finish:** Review in Cursor → copy to LinkedIn.

To create this automation in Cursor: ask *“Open Automations editor with PVMath weekly content draft”* after committing these files.

---

## `/loop` alternative (local)

In Cursor chat:

```
/loop 7d Read pvmath-marketing skill, run pvmath_content_bot.py, generate this week's LinkedIn posts (main + 2 variants each), save to marketing/drafts/
```

Runs every 7 days in this session. Stop when you say stop.

---

## Draft workflow

```
marketing/drafts/
  2026-06-23-weekly-assignment.md   ← bot output + agent prompt
  2026-06-24-tue-linkedin-approved.md  ← you paste winner after review
```

Gitignored: `marketing/drafts/*.md` (local working files). Commit skill + calendar + script to repo.

---

## Quality gate before publish

- [ ] Screening disclaimer if results discussed  
- [ ] No banned hype words  
- [ ] CTA matches funnel stage  
- [ ] Link to relevant guide when technical  
- [ ] Founder post: personal angle + one metric or workflow detail  

---

## Outbound email batch (Fridays)

Run bot with `--email` to add 3 cold-email variants targeting EPC civil teams. Send 5–10 manually; track replies in spreadsheet.

```bash
python3 scripts/pvmath_content_bot.py --email
```

---

## Instagram repurpose

Take **Variation A (short)** from Tue post → image quote card or carousel slide 1. Link in bio: pvmath.com/guides/
