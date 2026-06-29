# Cursor — Fresh Session Bootstrap Prompt

Use this when starting a brand-new Cursor chat (old chat got slow/bloated). Paste the block below as your first message. It tells Cursor to re-orient from the actual files on disk instead of relying on old chat memory, and hands it the current open work.

---

## Paste this into the new Cursor chat

```
This is a fresh chat — don't assume any context from earlier sessions. Re-orient yourself from the repo itself before doing anything:

1. Read CLAUDE.md at the repo root — it's the authoritative project memory (architecture, deployment, key files, known-bug history, git workflow).
2. Read PVMath/STATUS.md for the current business/priority snapshot.
3. Run `git log --oneline -15` and `git status` to see what's actually landed vs. what's still uncommitted — don't trust any stale plan or doc over what git actually shows.
4. Read docs/PVMath_Cursor_Brief_Unified_Report_Upgrade.md — the unified report rebuild it describes already shipped (commits 921f314, ef463c3, e05faf7, code lives in the new pvmath_reports/ package). Treat it as background, not a to-do list.

Then pick up this open work — these are confirmed bugs from reviewing two freshly-generated report PDFs, already grounded against the code, not guesses. Re-verify each against the current file state before fixing, since the repo may have moved since this was written:

**Bug 1 — "Utility-scale development potential (~0 MWp DC)" in the SiteIQ Key Drivers bullet, while the Project Summary table two inches above it on the same page shows the correct capacity range.**
File: pvmath_reports/siteiq_section.py, ~lines 99-118. `cap_for_suit` is hardcoded to `{"mwp_lo": 0, "mwp_hi": 0}` instead of copying the real values out of `cap` (which already holds the correct `mwp_range`). That zero flows into pvmath_reports/siteiq_suitability.py (~line 195), where the check is `is not None` — so 0 passes and renders as "~0 MWp DC" via `format_mwp_range()` in pvmath_capacity.py. Fix: pull `cap.get("mwp_lo")` / `cap.get("mwp_hi")` instead of hardcoding zero. After fixing, grep the rest of pvmath_reports/ for other hardcoded placeholder 0/None stubs — this is the second time a stub like this has shipped instead of the real wiring.

**Bug 2 — Est. DC capacity range is computed using Fixed Tilt density even when the project is Single-Axis Tracker.**
Confirmed on a 99.8 ha, Standard land use, Single-Axis Tracker project: report showed "~40–56 MWp DC." pvmath_capacity.py's own density table (`_BASE_DENSITY`) says Standard+Tracker = 0.35 MW/ha, which for 99.8 ha should give ~35–49 MWp. The reported 40–56 is an exact match for the Fixed Tilt density (0.40 MW/ha) on the same area — not a rounding artifact. Every function in pvmath_capacity.py silently defaults to `mount_type="Fixed Tilt"` when the mount value passed in is empty/falsy. Check pvmath_workflow/screen.py (~line 84, `mount = req.mount_type` at ~line 68) and pvmath_gate/analyze.py (~line 79, `mount = req.mount_type` at ~line 44) for wherever this report's capacity call sources its mount type — confirm it's never empty/None by the time it reaches screening_capacity(). This silently overstates tracker project capacity by ~15-20% versus what it should be — high priority, since it's a wrong number that looks plausible.

**Bug 3 (lower priority, wording not code) — German "Recommended Next Steps" EEG line.**
For ground-mount projects ≥1 MWp, German law requires winning a competitive BNetzA EEG-Ausschreugung (tender) before EEG remuneration applies — simple Marktstammdatenregister registration alone doesn't get a utility-scale project the EEG rate, that registration happens after winning a tender slot. Find wherever the German next-steps copy is generated (likely the same country-aware regulatory-guidance function referenced in CLAUDE.md, `assess_eeg()` / `get_next_steps()`) and make the wording conditional on project size — below 1 MWp can keep the current simple MaStR-registration phrasing; ≥1 MWp should reference the EEG-Ausschreibung process first.

**Item 4 (verify intent, not necessarily a bug) — Energy yield factor scoring 59/100 in the PVMATH SCORE table while every other factor sits 75-95 for an unremarkable, perfectly normal German tracker site (1387 kWh/kWp/yr, PR 85%).** Find wherever the Energy Yield factor score is computed and confirm whether it's meant to be benchmarked against a global reference (which would make a lower-resource market like Germany score lower by design — fine) versus a local/regional reference (which would mean 59 is wrong for this site). Report back what you find before changing anything — this might be correct behavior.

Give me a short plan (which files you'll touch, in what order) before making changes. Fix Bug 1 and Bug 2 first — both are visible on page 1 of any tracker-project report and actively damage credibility with prospects.
```

---

## Notes for next time

- This file itself is reusable — update the "open work" section each time a review surfaces new issues, and paste the updated block into the next fresh Cursor chat.
- Cursor chat history bloat happens because every previous message + file read stays in context. Starting a new chat and pointing it at CLAUDE.md / git log / specific file+line references (instead of re-pasting old conversation) is the fix — it gets full current context in 3-4 tool calls instead of inheriting thousands of stale tokens.
