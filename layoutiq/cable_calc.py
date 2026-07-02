"""Cable sizing — IEC 60364-5-52 ampacity + voltage drop (screening grade)."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

RHO_COPPER_20 = 0.0172  # Ω·mm²/m at 20°C
ALPHA_COPPER = 0.00393
STANDARD_SIZES_MM2 = [4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240]

# IEC 60364-5-52 Table B.52.1 — single-core DC, 90°C XLPE, Method E (cable tray)
AMPACITY = {
    4: 45,
    6: 58,
    10: 80,
    16: 107,
    25: 142,
    35: 174,
    50: 211,
    70: 269,
    95: 328,
    120: 382,
    150: 441,
    185: 506,
    240: 599,
}


def size_cable(
    current_A: float,
    length_m: float,
    voltage_V: float,
    *,
    max_vdrop_pct: float = 1.0,
    T_operating: float = 70.0,
) -> Dict[str, Any]:
    rho_t = RHO_COPPER_20 * (1.0 + ALPHA_COPPER * (T_operating - 20.0))
    for size in STANDARD_SIZES_MM2:
        if current_A > AMPACITY[size] * 0.87:
            continue
        vdrop_v = (2.0 * length_m * current_A * rho_t) / size
        vdrop_pct = vdrop_v / max(voltage_V, 1.0) * 100.0
        if vdrop_pct <= max_vdrop_pct:
            return {
                "size_mm2": size,
                "vdrop_pct": round(vdrop_pct, 2),
                "vdrop_V": round(vdrop_v, 2),
                "ampacity_derated": round(AMPACITY[size] * 0.87, 1),
                "length_m": round(length_m, 1),
                "current_A": round(current_A, 1),
            }
    return {
        "size_mm2": 240,
        "vdrop_pct": None,
        "warning": "Exceeds 240 mm² — split circuit or check design",
        "length_m": round(length_m, 1),
        "current_A": round(current_A, 1),
    }


def combiner_count(
    total_strings: int,
    inverter_type: str,
    strings_per_combiner: int = 12,
) -> Dict[str, Any]:
    if inverter_type == "string":
        return {
            "combiners_needed": 0,
            "strings_per_combiner": 0,
            "note": "String inverters — no DC combiner required",
            "combiner_spec": None,
            "unit_cost_eur_band": None,
        }
    n = int(math.ceil(total_strings / max(strings_per_combiner, 1)))
    return {
        "combiners_needed": n,
        "strings_per_combiner": strings_per_combiner,
        "note": None,
        "combiner_spec": (
            f"DC string combiner, {strings_per_combiner} inputs, 1500V rated, "
            "with string fuses and surge protection"
        ),
        "unit_cost_eur_band": "€800–1,500",
    }


def _avg_string_run_m(layout: Optional[Dict[str, Any]], pitch_m: float, modules_per_string: int) -> float:
    if layout and layout.get("rows_data"):
        lengths = [float(r.get("length_m") or 0) for r in layout["rows_data"]]
        avg_row = sum(lengths) / len(lengths) if lengths else pitch_m * 10
        return max(15.0, avg_row * 0.5 + pitch_m * modules_per_string / 4.0)
    return max(20.0, pitch_m * modules_per_string / 2.0)


def compute_cable_bom(
    *,
    string_sizing: Dict[str, Any],
    module: Dict[str, Any],
    inverter: Dict[str, Any],
    layout: Optional[Dict[str, Any]] = None,
    pitch_m: float = 6.0,
    area_ha: float = 1.0,
    strings_per_combiner: int = 12,
    ac_run_m: float = 50.0,
    lv_voltage_v: float = 400.0,
) -> Dict[str, Any]:
    isc = float(module["Isc"])
    string_current = isc * 1.25
    mps = int(string_sizing["modules_per_string"])
    vmp_stc = float(module["Vmp"])
    string_voltage = vmp_stc * mps
    avg_run = _avg_string_run_m(layout, pitch_m, mps)
    total_strings = int(string_sizing["total_strings"])

    dc_string = size_cable(string_current, avg_run, string_voltage, max_vdrop_pct=1.0)
    dc_string["total_length_m"] = round(total_strings * avg_run * 2.0, 0)
    dc_string["spec"] = "IEC 62930 / EN 50618 single-core XLPE DC cable, 1500V rated"

    dc_main: Optional[Dict[str, Any]] = None
    combiner = combiner_count(total_strings, str(inverter.get("type", "string")), strings_per_combiner)
    if inverter.get("type") == "central" and combiner["combiners_needed"]:
        strings_per_cb = strings_per_combiner
        main_current = strings_per_cb * string_current
        main_length = max(30.0, math.sqrt(area_ha * 10_000.0) / 4.0)
        dc_main = size_cable(main_current, main_length, string_voltage, max_vdrop_pct=1.5)
        dc_main["total_length_m"] = round(combiner["combiners_needed"] * main_length * 2.0, 0)
        dc_main["spec"] = "IEC 60502-1 single-core XLPE DC cable, 1500V rated"

    paco_kw = float(inverter["Paco_kW"])
    n_inv = int(string_sizing["n_inverters"])
    ac_current = (paco_kw * 1000.0) / (math.sqrt(3.0) * lv_voltage_v * 0.99)
    ac_lv = size_cable(ac_current, ac_run_m, lv_voltage_v, max_vdrop_pct=1.0)
    ac_lv["total_length_m"] = round(n_inv * ac_run_m * 3.0, 0)
    ac_lv["spec"] = "IEC 60502-1 three-core XLPE, 0.6/1 kV"

    return {
        "dc_string_cable": dc_string,
        "dc_main_cable": dc_main,
        "ac_lv_cable": ac_lv,
        "combiner": combiner,
    }
