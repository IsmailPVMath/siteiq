# Cursor — Fresh Session Bootstrap Prompt

Use this whenever starting a brand-new Cursor chat (old one got slow/bloated). Paste the block below as your first message. It re-orients Cursor from the actual repo state — no old bug lists, no stale context carried forward.

---

## Paste this into the new Cursor chat

```
Fresh chat — ignore any earlier conversations, re-orient entirely from the repo itself:

1. Read CLAUDE.md at the repo root — authoritative project memory (architecture, deployment, key files, bug history, git workflow).
2. Read PVMath/STATUS.md for the current business/priority snapshot.
3. Run `git log --oneline -20` and `git status` to see what's actually landed vs. uncommitted.

Give me a short summary: what's currently working, what's mid-flight (uncommitted/staged but not on main), and what you'd flag as next priorities based on STATUS.md. Then wait for me to tell you what to work on — don't start changing anything yet.

Standing rules: staging branch first for day-to-day fixes, main is frozen unless I explicitly say promote to production. Confirm you've read the git-workflow section in CLAUDE.md before touching either branch.
```

---

## Notes for next time

- Cursor chat slowness comes from accumulated history (every prior message + file read stays in context). A new chat + pointing at CLAUDE.md/git log instead of re-pasting old conversation fixes it in 3-4 tool calls.
- Keep this prompt generic and bug-free — it's a reusable reset, not a task brief. If there's a specific fix to hand off, write a separate one-off brief (see docs/PVMath_Cursor_Brief_Unified_Report_Upgrade.md for the pattern) instead of folding it into this file.
