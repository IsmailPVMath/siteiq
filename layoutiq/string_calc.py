"""String sizing — temperature-corrected Voc/Vmp and inverter count."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


def get_temp_defaults(lat: float) -> Dict[str, float]:
    if lat > 50:
        return {"T_min": -15.0, "T_max": 35.0}
    if lat > 35:
        return {"T_min": -5.0, "T_max": 40.0}
    if lat > 20:
        return {"T_min": 5.0, "T_max": 45.0}
    return {"T_min": 10.0, "T_max": 50.0}


def temp_from_tmy(tmy_t2m: Optional[List[float]]) -> Dict[str, float]:
    if not tmy_t2m:
        return {}
    vals = [float(x) for x in tmy_t2m if x is not None]
    if not vals:
        return {}
    return {"T_min": min(vals), "T_max": max(vals)}


def voc_at_temp(voc_stc: float, beta_voc: float, t_amb: float) -> float:
    return voc_stc * (1.0 + beta_voc * (t_amb - 25.0))


def vmp_at_temp(vmp_stc: float, beta_vmp: float, t_cell: float) -> float:
    return vmp_stc * (1.0 + beta_vmp * (t_cell - 25.0))


def cell_temp_hot(t_amb_max: float, t_noct: float) -> float:
    return t_amb_max + (t_noct - 20.0) / 0.8


def voc_margin_pct(voc_max_string: float, v_system: float) -> float:
    return round((v_system - voc_max_string) / max(v_system, 1.0) * 100.0, 2)


def apply_voc_headroom(
    n_rec: int,
    *,
    voc_max_cell: float,
    v_system: float,
    n_min: int,
) -> tuple[int, bool]:
    """Reduce string length while Voc_max exceeds 98% of system voltage (2% headroom)."""
    applied = False
    while n_rec > n_min:
        if voc_max_cell * n_rec <= 0.98 * v_system:
            break
        n_rec -= 1
        applied = True
    return n_rec, applied


def compute_string_sizing(
    *,
    total_modules: int,
    dc_kwp: float,
    module: Dict[str, Any],
    inverter: Dict[str, Any],
    module_name: str,
    inverter_name: str,
    system_voltage_v: int = 1500,
    dc_ac_ratio: float = 1.20,
    lat: Optional[float] = None,
    tmy_t2m: Optional[List[float]] = None,
    is_tracker: bool = False,
) -> Dict[str, Any]:
    temps = temp_from_tmy(tmy_t2m) or get_temp_defaults(lat or 45.0)
    t_amb_min = float(temps["T_min"])
    t_amb_max = float(temps["T_max"])

    voc_stc = float(module["Voc"])
    vmp_stc = float(module["Vmp"])
    isc_stc = float(module["Isc"])
    beta_voc = float(module.get("beta_Voc", -0.0026))
    beta_vmp = float(module.get("beta_Vmp", -0.0028))
    t_noct = float(module.get("T_NOCT", 43))

    voc_max_cell = voc_at_temp(voc_stc, beta_voc, t_amb_min)
    t_cell_max = cell_temp_hot(t_amb_max, t_noct)
    vmp_min_cell = vmp_at_temp(vmp_stc, beta_vmp, t_cell_max)

    v_system = min(system_voltage_v, int(inverter.get("Vdcmax", system_voltage_v)))
    n_max = max(1, int(math.floor(v_system / voc_max_cell)))
    n_min = max(1, int(math.ceil(float(inverter["Mppt_low"]) / max(vmp_min_cell, 0.1))))
    n_rec = min(n_max, int(math.floor(float(inverter["Mppt_high"]) / max(vmp_stc, 0.1))))

    warnings: List[str] = []
    if n_rec < n_min:
        warnings.append(
            f"No valid string length: recommended {n_rec} modules/string "
            f"but MPPT minimum needs {n_min}. Check module/inverter compatibility."
        )
        n_rec = max(n_min, n_max)

    n_rec, voc_headroom_applied = apply_voc_headroom(
        n_rec, voc_max_cell=voc_max_cell, v_system=v_system, n_min=n_min
    )

    total_strings = int(math.ceil(total_modules / n_rec)) if total_modules else 0

    target_ratio = dc_ac_ratio
    if is_tracker and dc_ac_ratio == 1.20:
        target_ratio = max(1.15, min(1.25, dc_ac_ratio))
    elif not is_tracker:
        target_ratio = max(1.10, min(1.20, dc_ac_ratio))

    ac_needed_kw = dc_kwp / target_ratio if target_ratio else dc_kwp
    n_inverters = max(1, int(math.ceil(ac_needed_kw / float(inverter["Paco_kW"])))) if dc_kwp else 0
    actual_ac_kw = n_inverters * float(inverter["Paco_kW"])
    actual_dc_ac = round(dc_kwp / actual_ac_kw, 3) if actual_ac_kw else 0.0

    strings_per_mppt_actual: Optional[int] = None
    mppt_overload = False
    if inverter.get("type") == "string":
        total_mppts = n_inverters * int(inverter.get("n_mppt") or 1)
        strings_per_mppt_actual = max(1, int(math.ceil(total_strings / max(total_mppts, 1))))
        limit = inverter.get("strings_per_mppt")
        if limit and strings_per_mppt_actual > int(limit):
            mppt_overload = True
            warnings.append(
                f"Strings per MPPT ({strings_per_mppt_actual}) exceeds inverter limit ({limit})."
            )

    voc_max_string = voc_max_cell * n_rec
    vmp_op_string = vmp_stc * n_rec
    vmp_min_string = vmp_min_cell * n_rec
    margin_pct = voc_margin_pct(voc_max_string, v_system)
    margin_low = margin_pct < 3.0

    if voc_headroom_applied:
        warnings.append(
            f"String length reduced for 2% Voc headroom — margin now {margin_pct:.1f}% "
            f"({n_rec} modules/string)."
        )
    elif margin_low:
        warnings.append(
            f"Low Voc margin ({margin_pct:.1f}% at coldest temperature — recommend ≥3%)."
        )

    valid = voc_max_string <= v_system and vmp_min_string >= float(inverter["Mppt_low"])
    if voc_max_string > v_system:
        warnings.append(f"String Voc max {voc_max_string:.0f} V exceeds system limit {v_system} V.")
    if vmp_min_string < float(inverter["Mppt_low"]):
        warnings.append(
            f"String Vmp min {vmp_min_string:.0f} V below MPPT low {inverter['Mppt_low']} V."
        )

    return {
        "system_voltage_V": v_system,
        "modules_per_string": n_rec,
        "total_strings": total_strings,
        "n_inverters": n_inverters,
        "inverter_model": inverter_name,
        "module_model": module_name,
        "inverter_type": inverter.get("type", "string"),
        "dc_ac_ratio_target": target_ratio,
        "dc_ac_ratio": actual_dc_ac,
        "Voc_max_cell_V": round(voc_max_cell, 2),
        "Vmp_min_cell_V": round(vmp_min_cell, 2),
        "Voc_max_string_V": round(voc_max_string, 1),
        "Vmp_op_string_V": round(vmp_op_string, 1),
        "Vmp_min_string_V": round(vmp_min_string, 1),
        "voc_margin_pct": margin_pct,
        "voc_margin_low": margin_low,
        "voc_headroom_applied": voc_headroom_applied,
        "string_Isc_A": round(isc_stc, 2),
        "T_amb_min_used": t_amb_min,
        "T_amb_max_used": t_amb_max,
        "T_cell_max_used": round(t_cell_max, 1),
        "strings_per_mppt": strings_per_mppt_actual,
        "mppt_overload": mppt_overload,
        "valid": valid,
        "warnings": warnings,
    }
