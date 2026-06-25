# PVMath presentation master prompt

Use this prompt in Cursor (or any LLM) to regenerate or extend PVMath `.pptx` decks. The repo also ships an automated generator — prefer that for consistency.

## Brand (non-negotiable)

- **Colors:** PVMath green `#1d9e52` (accent), `#145f34` (headers), light green `#e8f5ee` (cards), text `#1a2e1a`
- **Do not** use generic McKinsey dark blue or corporate navy
- **Tagline:** From site to system.
- **Scope:** Ground-mount solar only — Fixed Tilt, Single-Axis Tracker, Standard and Agri-PV. No rooftop, carport, floating, BIPV.

## Honesty rules

- Early Access / screening-grade — not bankable yield, not survey-grade terrain
- No invented customer logos, case studies, or statistics
- Use placeholders: `[INSERT IMAGE]`, `[Customer name]`, `[Presenter name]`
- Compare vs **manual workflow** (GIS + PVGIS + spreadsheets), not named competitors unless verified
- Pricing: Free 5/module/mo · Pro €149/mo (75 pooled) · Developer €499/mo (300 pooled, 5 seats) · Enterprise custom

## Deck types

| Deck | Duration | Audience | Focus |
|------|----------|----------|-------|
| **sales-15** | ~15 min | EPC pre-sales, developers | All three modules + demo flow |
| **topoiq-30** | ~30 min | Civil, layout, structural | GLO-30, metrics, PDF/CAD exports |

## Slide requirements

Every slide must include:
1. Title + optional subtitle
2. 3–6 bullets max (readable at 3 m)
3. Speaker notes: duration (~sec), transition cue, talk track
4. Image placeholder label where visuals help
5. Anticipated Q&A on technical slides

## Automated generation (preferred)

```bash
pip install -r scripts/requirements-decks.txt
python scripts/generate_pvmath_deck.py --all
python scripts/generate_pvmath_deck.py --deck sales-15 --presenter "Your Name"
```

Output: `docs/decks/PVMath_Sales_15min.pptx`, `docs/decks/PVMath_TopoIQ_30min.pptx`

Edit slide content in:
- `pvmath_deck/content.py` — facts, demo steps, Q&A
- `pvmath_deck/decks/sales_15.py` — 15-min slide order
- `pvmath_deck/decks/topoiq_30.py` — 30-min slide order
- `pvmath_deck/builder.py` — layouts and styling

## Manual LLM prompt template

```
Generate speaker notes and bullet refinements for [sales-15 | topoiq-30].

Constraints:
- PVMath green brand, ground-mount only
- No invented stats or customer names
- Include disclaimer: screening-grade, not bankable/survey-grade
- Modules: SiteIQ (screening), TopoIQ (terrain + LandXML/DXF), YieldIQ (yield compare)

Current slide: [paste title + bullets]

Return: refined bullets (max 6), speaker notes (60–90 sec), 2 Q&A pairs, image placeholder label.
```

## Assets to insert manually after generation

- App screenshots (SiteIQ score, TopoIQ heatmap, YieldIQ chart)
- Sample PDF cover from `assets/sample-siteiq-report.pdf`
- Civil 3D LandXML import screenshot
- Optional: export `assets/logo.svg` to PNG for cover if shape logo is insufficient

## Links

- App: https://siteiq.pvmath.com
- Website: https://pvmath.com
- YouTube: https://www.youtube.com/@PVMath_Official
- Contact: contact@pvmath.com
