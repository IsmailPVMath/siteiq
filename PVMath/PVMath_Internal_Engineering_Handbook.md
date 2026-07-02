# PVMath Internal Engineering Handbook

```
⚠️ INTERNAL USE ONLY — CONFIDENTIAL
Owner: Mohammed Ismail Pasha (PVMath)
This document contains proprietary engineering methodology, formulas, and data source
configurations used internally by PVMath. It is not to be shared with users, customers,
or third parties. The user-facing Engineering Reference Manual is a separate document.
```

**Last updated:** 30 Jun 2026 — LayoutIQ Electrical Extension (staging)

Implementation files: `layoutiq/string_calc.py`, `layoutiq/cable_calc.py`, `layoutiq/electrical.py`, `layoutiq/equipment_db.py`, `layoutiq/sld.py`, `layoutiq/electrical_pdf.py`.

---

## 1. String voltage sizing

### String voltage sizing — Voc_max at coldest ambient

**What it computes:** Maximum number of modules per string limited by open-circuit voltage at the coldest expected ambient temperature.

**Formula:**

```
T_amb_min = min(TMY T2m)  OR latitude default (see §12)
Voc_max_cell = Voc_STC × (1 + β_Voc × (T_amb_min − 25))
n_max = floor(V_system / Voc_max_cell)
Voc_max_string = Voc_max_cell × n_modules
```

Where `β_Voc` is the fractional temperature coefficient per °C (curated modules store e.g. −0.0026 for −0.26%/°C), `V_system = min(user_system_voltage, inverter.Vdcmax)`.

**Constants and sources:**
- STC reference cell temperature: 25°C — IEC 61215:2021 test conditions.
- `β_Voc` from module datasheet / NREL CEC database via PVFree.

**Standard referenced:** IEC 61215:2021 — PV module qualification; Voc at STC.

**Engineering decision:** Voc correction uses linear coefficient (standard screening practice). Non-linear curves from manufacturer datasheets are not interpolated at screening stage.

**Assumptions and limitations:**
- Assumes uniform module temperature at open circuit (night/cold morning).
- Does not model potential-induced degradation or mismatch on Voc.
- Accuracy: ±5% on string count vs detailed design if TMY used; ±10% with latitude defaults.

**Data source:** PVGIS TMY `T2m` when passed from YieldIQ; else `get_temp_defaults(lat)` in `string_calc.py`.

---

## 2. MPPT window validation

### MPPT window validation — Vmp at hottest cell

**What it computes:** Minimum modules per string so operating voltage stays above inverter MPPT lower limit at hot cell temperature.

**Formula:**

```
T_cell_max = T_amb_max + (T_NOCT − 20) / 0.8
Vmp_min_cell = Vmp_STC × (1 + β_Vmp × (T_cell_max − 25))
n_min = ceil(Mppt_low / Vmp_min_cell)
n_rec = min(n_max, floor(Mppt_high / Vmp_STC))
valid ⟺ Voc_max_string ≤ V_system AND Vmp_min_string ≥ Mppt_low
```

**Constants and sources:**
- NOCT model divisor 0.8 — simplified Faiman/NOCT correlation at 1000 W/m² (screening).
- `Mppt_low`, `Mppt_high` from inverter CEC database.

**Standard referenced:** IEC 62109 / inverter datasheet MPPT range.

**Engineering decision:** Upper string length capped by `Mppt_high / Vmp_STC` (not hot Vmp) to avoid exceeding MPPT voltage at moderate temperatures while maximizing string length for cable loss.

**Assumptions and limitations:**
- Hot-cell model does not use wind speed from TMY.
- If `n_rec < n_min`, code flags warning and clamps — user must change module/inverter pairing.

---

## 3. Cable ampacity

### Cable ampacity — IEC 60364-5-52 Method E

**What it computes:** Minimum copper cross-section meeting thermal limit for DC string, DC main, and AC LV segments.

**Formula:**

```
For each size in STANDARD_SIZES_MM2:
  reject if I > AMPACITY[size] × 0.87
```

**Constants and sources:**
- `AMPACITY` table — IEC 60364-5-52 Table B.52.1, single-core XLPE 90°C, Method E (cable tray).
- Derating factor **0.87** — accounts for 70°C ambient / grouping margin at screening (no site-specific derating study).

**Standard referenced:** IEC 60364-5-52:2018, Table B.52.1 — Current-carrying capacity.

**Engineering decision:** Method E (tray) chosen as default for ground-mount utility DC homeruns between combiners and inverters. Underground Method D not modelled (requires soil ρ).

**Assumptions and limitations:**
- Copper conductor, XLPE 90°C.
- Parallel cables not modelled — single conductor per pole.
- Accuracy: ±15% vs detailed cable schedule.

---

## 4. Cable voltage drop

### Cable voltage drop — DC two-wire loss

**What it computes:** Resistive voltage drop to confirm size meets % limit.

**Formula:**

```
ρ_T = RHO_COPPER_20 × (1 + ALPHA_COPPER × (T_oper − 20))
V_drop = 2 × L × I × ρ_T / A_mm²
V_drop_pct = V_drop / V_circuit × 100
```

**Constants and sources:**
- `RHO_COPPER_20 = 0.0172 Ω·mm²/m` — IEC 60287-1-1:2006 Table 1 (annealed copper).
- `ALPHA_COPPER = 0.00393 /°C` — same source.
- `T_oper = 70°C` default for buried/tray DC runs.

**Thresholds:**
- DC string: **1.0%** of string Vmp.
- DC main (central): **1.5%**.
- AC LV: **1.0%** at 400 V line-line equivalent.

**Engineering decision:** Factor 2× length for DC positive + negative conductor. AC uses three-phase equivalent current `I = P / (√3 × V × PF)`.

---

## 5. DC:AC ratio defaults

### DC:AC ratio — inverter count

**What it computes:** Number of inverters from target DC:AC and module DC capacity.

**Formula:**

```
ac_needed_kW = dc_kwp / target_dc_ac
n_inverters = ceil(ac_needed_kW / Paco_kW)
actual_dc_ac = dc_kwp / (n_inverters × Paco_kW)
```

**Defaults:**
- User default **1.20**.
- SAT clamp 1.15–1.25 when default 1.20 selected.
- FT clamp 1.10–1.20.

**Engineering decision:** Aligns with NREL/SAM screening practice and IEA PVPS Task 13 guidance for utility overbuild. Exact inverter count uses `ceil` — actual ratio may be slightly below target (conservative AC side).

---

## 6. Isc safety factor (1.25×)

### String protection current — 1.25 × Isc

**What it computes:** Design current for cable ampacity and fuse screening.

**Formula:**

```
I_design = Isc_STC × 1.25
```

**Standard referenced:** NEC 690.8(A); IEC 62548:2016 §10.3.1 — overcurrent device sizing vs module Isc.

**Engineering decision:** 1.25× applied to all DC string and combiner main calculations. No fuse sizing output (FEED excluded).

---

## 7. Combiner box string count default (12)

### Combiner count — central inverters only

**Formula:**

```
if inverter.type == "string": combiners = 0
else: combiners = ceil(total_strings / strings_per_combiner)
```

**Default `strings_per_combiner = 12`.**

**Engineering decision:** 12-input combiners are industry-standard utility units (1500 V, fused inputs). User can override 4–24 in UI. Unit cost band €800–1,500 documented in BOM text only (no pricing engine).

---

## 8. Inverter placement algorithm

### Spatial drawing — row-block centroids

**What it computes:** Indicative inverter station positions on A1 Page 2.

**Algorithm:**
1. Split `rows_data` into `n_inverters` contiguous blocks.
2. Place symbol at block centroid + 8 m offset (service road assumption).
3. Central inverters: larger symbol at site centroid when `n_inverters` small.

**Assumptions and limitations:**
- Not road-network aware; irregular parcels may misplace symbols.
- 8 m offset is typical SAT maintenance road — not validated per site.

---

## 9. Cable length estimation

### Hom run length from layout geometry

**String homerun:**

```
avg_run_m = max(15, avg_row_length × 0.5 + pitch × modules_per_string / 4)
total_string_cable_m = total_strings × avg_run_m × 2  (+/− conductors)
```

**DC main (central):**

```
main_length_m = max(30, sqrt(area_ha × 10_000) / 4)
```

**AC LV:** `n_inverters × ac_run_m × 3` (default `ac_run_m = 50 m`).

**Accuracy:** ±25% vs as-built routing — screening label applied on all PDF outputs.

---

## 10. Module database source

**Primary API:** PVFree — `https://pvfree.azurewebsites.net/api/v1/cecmodule/`

**Search:** `GET /cecmodule/?format=json&Name__icontains={query}&limit=20`

**Fields mapped:** `V_oc_ref`, `V_mp_ref`, `I_sc_ref`, `I_mp_ref`, `beta_oc`, `alpha_sc`, `T_NOCT`.

**Fallback:** `layoutiq/equipment_db.py` `CURATED_MODULES` — five utility bifacial modules (580–695 Wp), verified against public datasheets Jun 2026.

**Update cadence:** Refresh curated list annually or on major module platform change. PVFree live on each search.

---

## 11. Inverter database source

**API:** `GET /api/v1/pvinverter/?format=json&Name__icontains={query}`

**Curated inverters:** Sungrow SG3125HV-30, Huawei SUN2000-196KTL, SMA STP 110-60, Fronius Tauro ECO 100 kW, GoodWe GW3600D-NS.

**Mppt_low / Mppt_high:** CEC test report values — physically the DC voltage window where the inverter MPPT operates. `Vdcmax` is absolute maximum input voltage (string Voc limit).

---

## 12. Temperature defaults by latitude

| Latitude band | T_min (°C) | T_max (°C) | Region example |
|---|---|---|---|
| > 50°N | −15 | 35 | Germany, UK, Canada south |
| 35–50°N | −5 | 40 | Central Europe, US mid-lat |
| 20–35°N | 5 | 45 | India, MENA, US South |
| ≤ 20°N | 10 | 50 | Equatorial |

Used when PVGIS TMY `T2m` not supplied. Conservative for Voc (cold) and Vmp (hot).

---

## 13. SLD topology logic

**String inverter:** `[PV Array] → String cables → [String INV × N] → AC bus → [MV XFMR 400/20 kV] → Grid`

**Central inverter:** `[PV Array] → String cables → [Combiner × N] → DC main → [Central INV] → AC → [MV XFMR] → Grid`

**Node voltages assumed:** 1500 V DC (or user 1000 V), 400 V AC LV (EU), 20 kV MV (EU screening default).

SVG generated in `layoutiq/sld.py`; embedded in A1 Page 2 sidebar note. Label: *Indicative SLD — Screening Grade*.

---

## 14. PVsyst loss defaults

| Loss | Default | Source / rationale |
|---|---|---|
| Soiling | 2.5% | Typical annual average — user must adjust by climate |
| DC wiring | from cable V_drop calc | LayoutIQ string + main % |
| Mismatch | 1.0% | IEA PVPS Task 13 typical |
| LID | 0.5% | Mono PERC/TOPCon first-year |
| Transformer | 0.8% | MV transformer nameplate |
| Availability | 98% | Utility-scale O&M screening |

**Export:** `{Project}_PVsyst_Input.txt` in project package ZIP + A1 Page 3 PDF. No `.PVC` file generation (PVsyst format undocumented/version-sensitive).

---

## Document control

| Version | Date | Author | Change |
|---|---|---|---|
| 0.1 | 30 Jun 2026 | M.I. Pasha | Initial LayoutIQ Electrical sections 1–14 |
