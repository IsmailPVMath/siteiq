# Cursor Brief — RevenueIQ Full Feature Build

> **Status:** v0 backend skeleton exists (`revenueiq/engine.py`, `revenueiq/tariffs.py`, `revenueiq/capex.py`).
> This brief upgrades it to a full user-facing module: CAPEX breakdown, OPEX, revenue, financial KPIs, sensitivity, PDF section, score factor.
> **Branch:** staging only. `PVMATH_ENABLE_REVENUEIQ=1` on `cozy-enjoyment`. Never touch main or pvmath.com until owner says promote.

---

## 0. Design rules (read before touching anything)

- **All financial outputs are BANDS, not point estimates.** Always show a low/high range (e.g. "€420–580/kWp"), never a single precise figure. The UI must communicate this is screening-grade, not a bankable study.
- **No bankability claims.** Disclaim clearly that IRR/NPV/LCOE are indicative — a full project finance model requires PVsyst-grade yield, detailed cost tenders, and legal/tax advice.
- **Inputs come from upstream modules only** — dc_kwp from LayoutIQ, annual_mwh from YieldIQ, terrain_grade from TerrainIQ, country/land_use/mount_type from project setup. RevenueIQ never asks the user to re-enter data that's already in the system.
- **User overrides for key assumptions** — tariff/PPA rate, CAPEX per kWp, WACC, project lifetime. Show defaults pre-filled from the model; let user adjust and re-run. Store overrides per-project in the project record.
- **Multi-currency:** all financial outputs are computed in EUR internally and also shown in local currency (see §2.4). India → INR, US → USD, Australia → AUD, UK → GBP; all others → EUR. Use a static exchange rate table that the owner can update quarterly — not a live FX API.
- **Ground-mount only** — FT and SAT, Standard and Agri-PV. No rooftop, BESS, carport, floating.

---

## 1. Existing files — read these first before building anything

```
revenueiq/engine.py       # Main calculation engine (v0 — extend, don't rewrite)
revenueiq/tariffs.py      # Country-aware tariff table (extend with full country set)
revenueiq/capex.py        # CAPEX model (v0 — extend with component breakdown)
api/routers/revenueiq.py  # POST /api/v1/revenueiq/analyze (existing route)
```

Also check `api/schemas/workflow.py` for how upstream data flows, and `pvmath_workflow/project_report.py` for the PDF pattern (RevenueIQ section should follow the same flowables pattern as SiteIQ/TerrainIQ/YieldIQ sections in `pvmath_reports/`).

---

## 2. CAPEX model — component breakdown by mount type

Extend `revenueiq/capex.py`. CAPEX bands are per kWp DC and scale linearly with `dc_kwp`. Express as `{lo: float, hi: float}` in €/kWp. Final output: `total_capex_lo`, `total_capex_hi` in € (multiply by dc_kwp).

### Component table — use these as default ranges (2026 global benchmarks)

| Component | Fixed Tilt (€/kWp) | Single-Axis Tracker (€/kWp) | Notes |
|---|---|---|---|
| PV modules | 130–170 | 130–170 | Bifacial, 540–700 Wp, commodity price; same for both |
| Inverters / power conversion | 40–65 | 40–65 | String or central; same for both |
| Mounting structure | 55–85 | 130–170 | Tracker premium: motors, control, tracker posts |
| DC cabling + combiner | 20–35 | 20–35 | — |
| AC cabling + MV transformer | 25–45 | 25–45 | — |
| Civil works / earthworks | *terrain-adjusted* | *terrain-adjusted* | See §2.1 |
| Grid connection | *distance-adjusted* | *distance-adjusted* | See §2.2 |
| Engineering (FEED, detailed) | 15–25 | 15–25 | % of hardware |
| Permitting + development | 10–20 | 10–20 | Higher in DE/AT than ES/PL |
| Commissioning + testing | 8–15 | 8–15 | — |
| Contingency | 5% of sum above | 5% of sum above | Apply as multiplier at end |

**Country multiplier** (labor + logistics premium on top of hardware):
- DE, AT, CH: 1.15–1.25
- ES, IT, FR, PL: 1.00 (baseline)
- IN, AU: 0.80–0.95 (lower labor, different supply chain)
- US: 1.10–1.20

**Result band check (after applying country multiplier):**
- DE SAT: ~€580–850/kWp, FT: ~€480–720/kWp
- ES/IT SAT: ~€480–700/kWp, FT: ~€400–580/kWp
- US SAT: ~$700–1,050/kWp (~€640–960/kWp equiv.) — but owner's **effective CAPEX drops ~30%** after ITC credit (see §4.1)
- IN SAT: ~₹35–50/Wp (~€380–540/kWp equiv.), FT: ~₹30–42/Wp
- AU SAT: ~A$1.0–1.5/Wp (~€600–900/kWp equiv.), FT: ~A$0.85–1.25/Wp

If your numbers are outside ±20% of the relevant market range, check the country multiplier first.

### 2.1 Civil/earthworks — terrain_grade adjustment

`terrain_grade` comes from TerrainIQ `mean_slope` (%). Use a tiered cost model:

| Mean slope | Civil cost (FT, €/kWp) | Civil cost (SAT, €/kWp) | Notes |
|---|---|---|---|
| ≤ 2% | 25–45 | 30–55 | Minimal grading |
| 2–5% | 45–75 | 55–90 | Moderate earthworks |
| 5–10% | 75–130 | 90–160 | Significant cut/fill |
| > 10% | 130–200+ | Not recommended | Flag as cost risk |

If TerrainIQ hasn't run (no `terrain_grade`), use mid-range defaults and add a note: "Civil cost estimated at mid-range — run TerrainIQ for site-specific earthworks estimate."

### 2.2 Grid connection — distance-adjusted

Uses `grid_distance_km` from SiteIQ screening (OSM distance to nearest substation). MV cable estimate only — not HV line, not substation upgrade cost (disclaim accordingly).

| Distance | Grid connection cost (€/kWp) |
|---|---|
| < 1 km | 15–30 |
| 1–3 km | 30–60 |
| 3–7 km | 60–120 |
| > 7 km | 120–200+ (flag: verify with DSO) |

If `grid_distance_km` unavailable, use 50–80 €/kWp as default with caveat.

### 2.3 Agri-PV adjustment

If `land_use == "Agri-PV"`: multiply mounting structure cost by 1.5–1.8 (elevated bifacial racking, wider pitch, dual-use infrastructure). Civil costs are also higher (+20–30%). All other components unchanged.

### 2.4 Currency handling

All internal calculations use EUR. Final outputs are shown in **both EUR and local currency**. Use a static exchange rate table (owner updates quarterly — not a live FX API):

```python
# revenueiq/currency.py — static rates, owner updates each quarter
LOCAL_CURRENCY = {
    "DE": "EUR", "AT": "EUR", "CH": "CHF", "FR": "EUR", "IT": "EUR",
    "ES": "EUR", "PL": "PLN", "NL": "EUR", "BE": "EUR",
    "IN": "INR", "AU": "AUD", "NZ": "NZD",
    "US": "USD", "CA": "CAD", "MX": "MXN",
    "UK": "GBP", "GB": "GBP",
    "ZA": "ZAR", "NG": "NGN", "KE": "KES",
    "JP": "JPY", "KR": "KRW", "CN": "CNY",
    # default for unmapped countries: EUR
}

EUR_FX = {
    "USD": 1.08, "INR": 90.0, "AUD": 1.65, "GBP": 0.84,
    "CHF": 0.96, "PLN": 4.25, "CAD": 1.47, "NZD": 1.79,
    "ZAR": 20.0, "JPY": 162.0,
    # EUR → EUR = 1.0
}
```

In the API result and PDF, show: `€X–Y M` and `[LOCAL] X–Y M` side by side. For India, also show `₹X–Y Cr` (crore). For US tariff overrides, accept `$/MWh` and convert internally to €/MWh.

---

## 3. OPEX model — annual costs

Annual OPEX band in €/yr (also express per MWh: OPEX / annual_mwh).

| Item | Amount | Notes |
|---|---|---|
| O&M (preventive + corrective) | €8–14/kWp/yr | SAT slightly higher (+€1–2/kWp/yr for motor/control maintenance) |
| Land lease | Country-specific (§3.1) | Per ha/yr × site_area_ha |
| Insurance | 0.25–0.40% of CAPEX/yr | Property + liability + weather |
| Asset management | €2–4/kWp/yr | Remote monitoring, reporting, owner-side management |
| Grid access fees (metering, balancing) | €1–3/kWp/yr | Country-variable |
| **Total OPEX** | **~€13–23/kWp/yr** | Sum of above; scale with dc_kwp |

### 3.1 Land lease defaults (€/ha/yr)

| Country | Standard Ground Mount | Agri-PV |
|---|---|---|
| DE | 1,200–2,500 | 600–1,200 (farmer keeps agri income) |
| AT | 1,000–2,000 | 500–1,000 |
| ES | 400–900 | 200–500 |
| IT | 500–1,000 | 250–600 |
| FR | 400–800 | 200–400 |
| PL | 300–700 | 150–350 |
| IN | 100–250 | N/A |
| AU | 200–500 | N/A |
| US | 300–700 | N/A |

---

## 4. Revenue model — country-aware tariff

Extend `revenueiq/tariffs.py`. Revenue = tariff_rate × annual_mwh (Year 1), then degraded by 0.45%/yr for 25 years (bifacial standard degradation). Show cumulative 25-year revenue band.

### 4.1 Tariff/revenue modes

**Mode A — Government Auction / Feed-in Tariff (country-specific):**

Use Mode A when the project country has an active government-backed tender or FIT mechanism. `revenueiq/tariffs.py` selects the right row by `country` ISO code.

| Country | Mechanism | Indicative Rate (local) | EUR equiv. | Duration | Key caveat |
|---|---|---|---|---|---|
| DE | EEG Ausschreibung (BNetzA) | 4.6–5.2 ct/kWh | €46–52/MWh | 20 yr | ≥1 MWp ground-mount must win BNetzA tender; rate varies per round |
| AT | Ökostrom tender (OeMAG) | €50–70/MWh | €50–70/MWh | 20 yr | — |
| FR | CRE appel d'offres | €45–65/MWh | €45–65/MWh | 20 yr | ≥0.5 MWp ground-mount competes |
| IT | GSE Aste (FER2 decree) | €50–75/MWh | €50–75/MWh | 20 yr | — |
| PL | URE auction | PLN 180–250/MWh | €42–59/MWh | 15 yr | — |
| CH | KEV / direct marketing premium | CHF 70–100/MWh | €73–104/MWh | 20 yr | Historically oversubscribed; long waitlist |
| UK/GB | AR/CfD Allocation Round | £40–60/MWh | €46–70/MWh | 15 yr | Difference contract vs reference price |
| IN | SECI / MNRE / state DISCOM PPA | ₹2.20–3.50/kWh | €24–39/MWh | 25 yr | DISCOM creditworthiness is key project risk; state varies widely |
| AU | LGC (LRET) + wholesale electricity | LGC A$25–45 + pool A$50–90/MWh | €44–80/MWh combined | LGC until 2030 | Model merchant tail post-2030; LGC price uncertain after target hit |
| ES | No active FIT — see Mode B | PPA market | — | — | Spain closed RECORE FIT; all new projects use bilateral PPA |
| US | ITC (30% tax credit) + PPA | See ITC note below | — | — | ITC is a CAPEX reduction, NOT a revenue stream — do not model as €/MWh |
| Others | Use Mode B (PPA) or Mode C | — | — | — | — |

**US ITC note (IRA 2022 — critical for correct US numbers):**
The US 30% Investment Tax Credit applies to the owner's tax liability based on total installed CAPEX. It is **not** a per-MWh revenue stream. Model it as an effective CAPEX reduction:
```python
# US only — apply after gross CAPEX calculation
itc_rate = 0.30  # base rate; can reach 0.40–0.50 with domestic content / energy community adders
effective_capex = gross_capex * (1 - itc_rate)
# Use effective_capex in DCF, payback, and LCOE calculations for US projects
```
US projects should then use **Mode B (PPA)** for revenue. Display separately in CAPEX breakdown: "Gross CAPEX: $X M | ITC credit (30%): −$Y M | Effective CAPEX: $Z M."

Add disclaimer: "US ITC eligibility and percentage depend on prevailing wage, apprenticeship, domestic content, and energy community requirements under the IRA 2022. Consult a US tax advisor."

Add caveat text to PDF for Mode A: "Government auction rates are indicative benchmarks from 2024–2025 tender rounds. Actual awarded tariffs depend on competition, project timing, and regulatory changes. Projects must satisfy local eligibility criteria."

**Mode B — Corporate/Utility PPA (primary route for ES, US, IN, AU, and merchant markets):**
- Default PPA rate by country: ES €38–58/MWh; IT €48–68/MWh; FR €42–62/MWh; DE (corporate PPA) €48–70/MWh; IN ₹2.50–4.00/kWh; US $28–50/MWh; AU A$55–90/MWh
- Contract duration: 10–15 years typical; model merchant tail at −15% to PPA rate for years 11–25
- For India: show revenue in ₹ and € side by side

**Mode C — User override:**
- Let user input their own €/MWh rate and lock it. Label clearly as "Custom rate (user-defined)."

### 4.2 Annual revenue calculation

```
revenue_lo = tariff_lo_eur_mwh × annual_mwh_lo / 1000 × (1 - degradation_25yr_avg)
revenue_hi = tariff_hi_eur_mwh × annual_mwh_hi / 1000 × (1 - degradation_25yr_avg)
```

Where `annual_mwh_lo/hi` applies a ±7% band around YieldIQ's central estimate (represents P90 vs P10 uncertainty at screening stage).

---

## 5. Financial KPIs — indicative only

All of these are screening-grade. Compute and display with explicit "INDICATIVE" label.

### 5.1 LCOE

```
lifetime_energy_mwh = sum(annual_mwh × (1 - 0.0045)^yr, yr=0..24)
npv_opex = sum(annual_opex / (1 + wacc)^yr, yr=0..24)
lcoe_lo = (capex_lo + npv_opex_lo) / lifetime_energy_hi   # optimistic case
lcoe_hi = (capex_hi + npv_opex_hi) / lifetime_energy_lo   # conservative case
```

Show as "€X–Y/MWh" (and local currency equivalent). Indicative LCOE ranges for well-sited utility-scale ground-mount:

| Market | LCOE indicative range |
|---|---|
| DE | €40–75/MWh (high civil cost, good EEG tariff) |
| ES / IT | €28–52/MWh (excellent solar, competitive construction) |
| FR | €32–58/MWh |
| PL | €35–60/MWh |
| IN | ₹1.8–3.5/kWh (~€20–39/MWh) — lowest CAPEX + excellent irradiance |
| US | $28–55/MWh (~€26–51/MWh) on effective post-ITC CAPEX |
| AU | A$38–68/MWh (~€23–41/MWh) |

Flag if `lcoe_lo > tariff_hi` (uneconomic at any scenario). Flag if LCOE band is entirely below tariff band (very favorable — double-check inputs).

### 5.2 Simple payback

```
payback_lo = capex_lo / revenue_hi   # years
payback_hi = capex_hi / revenue_lo
```

Good utility-scale ground-mount: 7–12 years. Flag if > 15 years.

### 5.3 Project IRR (simplified DCF)

Use a 25-year NPV model. IRR = discount rate that makes NPV = 0.

```
cashflows = [-capex, revenue_yr1 - opex, ..., revenue_yr25 - opex + terminal_value]
terminal_value = 0  # conservative; can add scrap/repowering optionality later
irr = solve for r where NPV(cashflows, r) = 0
```

Show lo/hi IRR band using capex_hi/revenue_lo (conservative) and capex_lo/revenue_hi (optimistic).

**Indicative project IRR targets by market** (utility-scale ground-mount, standard conditions):
| Market | Target IRR range | Notes |
|---|---|---|
| DE / AT | 4.5–8% | Low risk, regulated, high civil cost |
| ES / IT / FR | 7–13% | Strong solar, PPA market, competitive EPC |
| PL | 6–10% | — |
| IN | 10–18% | Excellent solar, low CAPEX, higher WACC + offtake risk |
| US | 8–16% | ITC brings effective CAPEX down 30%; merchant/PPA risk |
| AU | 8–14% | LGC-supported, strong solar |

Derive `market_irr_floor` from `country` for viability logic (§7):
```python
MARKET_IRR_FLOOR = {
    "DE": 5.0, "AT": 5.0, "CH": 5.5,
    "ES": 7.0, "IT": 7.0, "FR": 6.5, "PL": 6.5,
    "IN": 9.0, "US": 7.5, "AU": 7.5,
    "default": 6.0
}
```

Flag if `irr_hi < market_irr_floor − 2pp` (very thin for this market). Flag if `irr_lo < 0%` (negative in bad case).

### 5.4 NPV

```
npv = sum(cashflows / (1 + wacc)^yr, yr=0..25)
```

Default WACC: 6.5% (Germany, conservative project finance). User-overridable.

### 5.5 Default WACC by country

| Country | WACC default |
|---|---|
| DE, AT | 6.0–7.5% |
| ES, IT, FR | 6.5–8.0% |
| PL | 7.5–9.0% |
| IN | 9.0–12.0% |
| AU | 7.0–9.0% |
| US | 6.5–8.5% |

---

## 6. Sensitivity table — mini tornado

Compute the impact on Project IRR of these four inputs, each ±10%:

| Variable | Shift | IRR impact |
|---|---|---|
| Energy yield (MWh/yr) | ±10% | Δ IRR (pp) |
| Total CAPEX | ±10% | Δ IRR (pp) |
| Tariff / PPA rate | ±10% | Δ IRR (pp) |
| OPEX | ±10% | Δ IRR (pp) |

Display as a 4-row table: Variable / Direction (↑↓) / IRR impact. No chart needed at this stage — a clear table is fine and renders in PDF without matplotlib. If any single variable drives > 3pp swing in IRR, label it "Key Risk Factor."

---

## 7. Economic Viability Card — on-screen

A color-coded summary card at the top of the RevenueIQ section. Three states.

First, derive `market_irr_floor` from `MARKET_IRR_FLOOR` dict (§5.3). Then evaluate:

| State | Condition | Color | Label |
|---|---|---|---|
| STRONG | LCOE_hi < tariff_lo AND IRR_lo > market_irr_floor | Green | "Strong economic case — proceed to FEED" |
| MARGINAL | LCOE overlaps tariff band OR IRR between (market_irr_floor − 3pp) and market_irr_floor | Amber | "Marginal — de-risk CAPEX and grid cost before committing" |
| THIN / FLAG | LCOE_lo > tariff_hi OR IRR_hi < (market_irr_floor − 3pp) | Red | "Thin margin — validate assumptions before advancing" |

This makes the viability verdict country-relative: a 7% IRR in India is thin; the same 7% in Germany is strong.

One-line supporting text: "At €[lcoe_lo]–[lcoe_hi]/MWh LCOE vs [tariff_lo]–[tariff_hi]/MWh available tariff, [state text]."

---

## 8. PDF section — add to unified report

Add a `build_revenueiq_flowables(req, result)` function in `pvmath_reports/` (create `pvmath_reports/revenueiq_section.py`). Follow the same structure as `pvmath_reports/siteiq_section.py` — return a list of ReportLab flowables, called from `pvmath_workflow/project_report.py::build_pvmath_report_pdf` after the YieldIQ section.

Section order in PDF:
1. Project Summary
2. SiteIQ
3. TerrainIQ
4. YieldIQ
5. **RevenueIQ** ← insert here
6. Disclaimers + Annex

### RevenueIQ PDF section content:
1. **CAPEX BREAKDOWN** — table with component rows and lo/hi columns (use Paragraph for all cells, same lp() helper)
2. **ANNUAL OPEX** — summary table (5 rows)
3. **REVENUE MODEL** — one table: tariff mode, rate, Year 1 revenue band, 25-yr cumulative band
4. **FINANCIAL INDICATORS** — 4-metric table: LCOE, Simple Payback, Project IRR, NPV at WACC
5. **SENSITIVITY** — 4-row table as described in §6
6. **ECONOMIC VIABILITY** — the colored verdict card (use colored Paragraph, no emoji)

No matplotlib chart needed for v1 of the PDF — all tables. Can add a cash-flow bar chart in v2.

**PDF disclaimer (add to Disclaimers section):**
> "RevenueIQ provides indicative financial screening only. CAPEX ranges are based on global benchmark data (2025–2026) adjusted for technology type, mount system, country, and market conditions; actual costs depend on site conditions, supply chain, and competitive EPC tender results. Revenue figures use indicative tariff and PPA benchmark rates — government auction projects must win the applicable tender round, and PPA rates depend on offtaker credit and market conditions at the time of contract. US ITC figures are indicative; eligibility and percentage depend on compliance with IRA 2022 requirements. All financial metrics (IRR, NPV, LCOE, payback) are screening-grade estimates only and are not bankable yield assessments. Engage a certified financial advisor and independent engineer before making any financial close or investment decision."

---

## 9. PVMath score integration — optional economic factor

If `revenueiq_result` is available, add "Economic viability" as a 7th factor in the PVMath score breakdown (page 7). Weight: **10/100** (reduce existing 6 factors proportionally, e.g. apply 0.90 multiplier to current weights so total stays 100).

Score mapping for Economic viability:
| Condition | Score |
|---|---|
| IRR_lo > 8% AND LCOE_hi < tariff_lo | 90–100 |
| IRR_lo 5–8% OR LCOE overlaps tariff | 70–89 |
| IRR_lo 3–5% | 50–69 |
| IRR_lo < 3% OR IRR_hi < 0 | 20–49 |
| Cannot compute (missing LayoutIQ/YieldIQ data) | null — exclude factor |

If RevenueIQ hasn't run, exclude Economic viability from score (don't penalize). Update the score caption: "Includes economic viability from RevenueIQ where available."

---

## 10. API schema — extend existing endpoint

`POST /api/v1/revenueiq/analyze` — extend request/response schema in `api/schemas/`:

```python
class RevenueIQRequest(BaseModel):
    # From upstream modules — all auto-populated from project state
    dc_kwp: float                          # from LayoutIQ
    annual_mwh: float                      # from YieldIQ
    site_area_ha: float                    # from project setup
    country: str                           # ISO 3166-1 alpha-2 or full name
    land_use: str                          # "Standard" | "Agri-PV"
    mount_type: str                        # "Fixed Tilt" | "Single-Axis Tracker"
    mean_slope_pct: float | None = None    # from TerrainIQ (for civil cost)
    grid_distance_km: float | None = None  # from SiteIQ (for grid connection cost)
    
    # User-overridable assumptions (front-end exposes these as editable inputs)
    wacc_pct: float = 6.5
    project_lifetime_yr: int = 25
    tariff_override_local_mwh: float | None = None  # in local currency/MWh; None = use country model
    capex_override_eur_kwp: float | None = None      # None = use component model
    itc_rate: float = 0.0                            # US only default 0.30; other markets 0.0

class RevenueIQResult(BaseModel):
    # Currency context
    local_currency: str          # ISO 4217: "EUR", "USD", "INR", "AUD", "GBP", etc.
    eur_fx_rate: float           # local units per EUR (e.g. INR: 90.0, USD: 1.08)
    
    # CAPEX
    capex_lo_eur: float
    capex_hi_eur: float
    capex_lo_local: float        # capex_lo_eur × eur_fx_rate
    capex_hi_local: float
    capex_breakdown: dict        # component → {lo_eur, hi_eur, lo_local, hi_local}
    itc_credit_eur: float        # 0 for non-US; shown separately in US CAPEX card
    effective_capex_lo_eur: float  # gross CAPEX − ITC credit (lo)
    effective_capex_hi_eur: float
    
    # OPEX
    opex_lo_eur_yr: float
    opex_hi_eur_yr: float
    opex_lo_local_yr: float
    opex_hi_local_yr: float
    
    # Revenue
    tariff_mode: str        # "GOVT_AUCTION" | "PPA" | "CUSTOM"
    tariff_lo_eur_mwh: float
    tariff_hi_eur_mwh: float
    tariff_lo_local_mwh: float
    tariff_hi_local_mwh: float
    revenue_yr1_lo_eur: float
    revenue_yr1_hi_eur: float
    revenue_25yr_lo_eur: float
    revenue_25yr_hi_eur: float
    
    # KPIs
    lcoe_lo_eur_mwh: float
    lcoe_hi_eur_mwh: float
    payback_lo_yr: float
    payback_hi_yr: float
    irr_lo_pct: float
    irr_hi_pct: float
    npv_lo_eur: float
    npv_hi_eur: float
    
    # Sensitivity (IRR change in percentage points per ±10% variable shift)
    sensitivity: dict   # {"yield": float, "capex": float, "tariff": float, "opex": float}
    
    # Viability verdict
    viability: str      # "STRONG" | "MARGINAL" | "THIN"
    viability_note: str
    economic_score: int # 0–100 for PVMath score integration
```

---

## 11. Frontend — RevenueIQ step in the workflow

Add RevenueIQ as a new step in the React workflow (`frontend/src/pages/`) after YieldIQ, following the same step-page pattern. 

The page should:
1. Auto-run the analysis on entry (same as YieldIQ) using project state — no extra user input needed for first run
2. Show the Economic Viability Card prominently at top (colored, high-impact)
3. Show 4 financial KPI cards (LCOE, Payback, IRR, NPV) in the same style as YieldIQ's metric cards
4. Below KPIs: collapsible "CAPEX Breakdown" table and "Assumptions" panel with user-override inputs (WACC, project lifetime, tariff rate, CAPEX override)
5. "Recalculate" button on Assumptions panel — re-POSTs to API with overridden values and refreshes all numbers
6. Sensitivity table (4 rows, compact)
7. Standard disclaimer text at bottom

**Navigation guard:** if LayoutIQ hasn't been run (no `dc_kwp`), show a locked state: "Run LayoutIQ first to get your installed capacity — RevenueIQ needs it to compute CAPEX and IRR."

---

## 12. What NOT to build in v1

- No BESS / battery storage revenue stacking
- No debt/equity split (show project-level IRR only, not equity IRR)
- No tax model (corporate tax, depreciation, MACRS, etc.)
- No grid augmentation or curtailment modeling
- No PPA tenor optimization
- No repowering / residual value model
- No multi-scenario comparison (v2)
- No matplotlib chart in PDF (v2 add-on)

---

## 13. Benchmark sanity checks — run these after build

Generate a test report for a well-known scenario and verify outputs land in expected range:

**Test A — Germany, 50 ha, SAT, ~14 MWp DC, ~19,000 MWh/yr (Bavaria, PVGIS-SARAH2):**
- CAPEX: expect €8.2–12.0M total (€580–850/kWp)
- OPEX: expect €180k–280k/yr
- Revenue (EEG 4.7 ct/kWh): ~€890k/yr Year 1
- LCOE: expect €38–65/MWh
- Payback: expect 9–14 years
- IRR: expect 4.5–8% (Germany low-yield, high civil cost)
- Viability: MARGINAL to STRONG depending on tariff won

**Test B — Spain, 100 ha, SAT, ~35 MWp DC, ~70,000 MWh/yr:**
- CAPEX: expect €17–25M total (€480–700/kWp)
- LCOE: expect €25–45/MWh
- IRR: expect 9–14%
- Viability: STRONG

**Test C — India, 200 ha, SAT, ~50 MWp DC, ~88,000 MWh/yr (Rajasthan, ~1,750 kWh/kWp):**
- Gross CAPEX: expect ₹175–250 Cr (~€19–28M), ~₹35–50/Wp
- Effective CAPEX: same (no ITC in India)
- OPEX: expect ₹4–7 Cr/yr (~€440k–780k/yr)
- Revenue (SECI/DISCOM PPA ₹2.50/kWh): ~₹22 Cr/yr Year 1 (~€2.4M/yr)
- LCOE: expect ₹1.8–3.2/kWh
- Payback: expect 8–12 years
- IRR: expect 10–16%
- Viability card: STRONG (market_irr_floor = 9% for IN)

**Test D — US, 120 ha, SAT, ~30 MWp DC, ~57,000 MWh/yr (Texas, ~1,900 kWh/kWp):**
- Gross CAPEX: expect $21–33M ($700–1,100/kWp)
- ITC credit (30%): −$6.3–9.9M
- Effective CAPEX: ~$14.7–23.1M ($490–770/kWp)
- OPEX: expect $250k–420k/yr
- Revenue (PPA $38/MWh): ~$2.2M/yr Year 1
- LCOE (on effective CAPEX): expect $28–52/MWh
- Payback (effective): expect 7–12 years
- IRR (on effective CAPEX): expect 9–15%
- Viability card: STRONG (market_irr_floor = 7.5% for US)

If any test falls significantly outside these ranges, debug the country multiplier or ITC handling first.

---

## 14. Staging gate — before promoting to main

- [ ] Tests A, B, C, D all produce numbers within expected ranges
- [ ] India project (Test C): output shows ₹ and € side by side; LCOE in ₹/kWh
- [ ] US project (Test D): ITC credit shown separately; effective CAPEX used in DCF; tariff in $/MWh
- [ ] Override inputs (WACC, tariff, CAPEX) recalculate correctly
- [ ] PDF section renders without overflow or emoji (no emoji anywhere in ReportLab)
- [ ] PVMath score updates when RevenueIQ result is present; stays 6-factor when absent
- [ ] `PVMATH_ENABLE_REVENUEIQ=0` on prod env — endpoint returns 404, no frontend step visible
- [ ] No mention of RevenueIQ on pvmath.com, index.html, or marketing pages

Tell me before promoting to main — I will verify one full report PDF end-to-end first.
