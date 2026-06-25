# PVMath presentation decks

Automated PowerPoint generator for customer-facing decks.

## Quick start

```bash
cd ~/Desktop/solarscout
pip install -r scripts/requirements-decks.txt
python scripts/generate_pvmath_deck.py --all
```

Outputs land in `docs/decks/`:

| File | Length | Use case |
|------|--------|----------|
| `PVMath_Sales_15min.pptx` | ~15 min | EPC / developer intro — SiteIQ, TopoIQ, YieldIQ |
| `PVMath_TopoIQ_30min.pptx` | ~30 min | Technical deep-dive — terrain, exports, CAD |

## Options

```bash
python scripts/generate_pvmath_deck.py --deck sales-15
python scripts/generate_pvmath_deck.py --deck topoiq-30 --presenter "Jane Doe" --date "19 June 2026"
python scripts/generate_pvmath_deck.py --out ./my-decks
```

## After generation

1. Open in PowerPoint / Keynote / Google Slides
2. Replace `[INSERT IMAGE]` placeholders with screenshots
3. Hide or delete the appendix slide (speaker script) before presenting
4. Optional: add logo PNG from `assets/logo.svg`

## Editing content

- **Facts & Q&A:** `pvmath_deck/content.py`
- **Slide order:** `pvmath_deck/decks/sales_15.py`, `topoiq_30.py`
- **Visual theme:** `pvmath_deck/theme.py`
- **Layouts:** `pvmath_deck/builder.py`

See `master_prompt.md` for LLM-assisted refinements.

## Note

Deck dependencies (`python-pptx`) are separate from Railway app requirements — not deployed to production.
