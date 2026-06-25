# PVMath documentation

## Founder Handbook (`PVMath/`)

Internal ops manual — formation, finance, legal mirrors, accounting, tax notes.

```bash
python3 scripts/generate_founder_handbook.py   # sync invoice template, verify folders
```

Drop official **Gewerbeanmeldung.pdf** and **Tax Registration.pdf** into `PVMath/Company Formation/` locally (gitignored).

## Manuals

| File | Audience | Safe to share? |
|------|----------|----------------|
| `PVMath_Engineering_Reference_Manual_INTERNAL.docx` | PVMath team only | **No** — contains proprietary weights, thresholds, and formulas |
| `PVMath_Engineering_Reference_Manual_PUBLIC.docx` | Customers, partners | **Yes** — concepts and definitions only; calculation fields redacted |
| `PVMath_Engineering_Reference_Manual.docx` | Legacy single file | Treat as **internal** if present |

Regenerate both editions (requires local `scripts/manual_terms_data.py` — not in git):

```bash
python3 scripts/generate_engineering_manual.py
```

**Git:** only `PVMath_Engineering_Reference_Manual_PUBLIC.docx` is committed. Internal manual and term corpus stay on your machine.

## Public vs internal content

- **Website Knowledge Centre** (`/guides/`) — Level 1 SEO-safe engineering concepts
- **In-app help** (`pvmath_help.py`) — Level 2 signed-in user guidance; no proprietary logic
- **Pro manual download** — Overview page; `can_download_engineering_manual()` in `pvmath_auth.py` (Professional+)
- **Internal manual** — Level 3 full implementation reference; never commit excerpts to public HTML

## What stays internal

- PVMath Score category weights and breakpoints
- Terrain score formula and penalty table
- Verdict trigger thresholds (cross-row p95, pct over 6%, etc.)
- GCR shading interpolation constants
- Grid auto-coarsen limits (`MAX_GRID_*`)
- Terrarium tile decode and zoom selection logic
