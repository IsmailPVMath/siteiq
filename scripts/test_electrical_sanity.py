#!/usr/bin/env python3
"""LayoutIQ electrical sanity checks — Tests A & B from the Cursor brief."""

from __future__ import annotations

import json
import math

from layoutiq.electrical import compute_electrical


def _synthetic_layout(total_modules: int, *, is_tracker: bool, area_ha: float = 50.0) -> dict:
    n_rows = max(1, total_modules // 28)
    return {
        "total_modules": total_modules,
        "total_rows": n_rows,
        "area_ha": area_ha,
        "is_tracker": is_tracker,
        "rows_data": [{"length_m": 120.0} for _ in range(n_rows)],
        "rows_polys": [],
    }


def run_test_a() -> dict:
    layout = _synthetic_layout(22580, is_tracker=True, area_ha=99.8)
    return compute_electrical(
        layout=layout,
        module_name="Jinko Tiger Neo N-type 620Wp",
        inverter_name="Sungrow SG3125HV-30 (3.125 MW, 1500V)",
        system_voltage_v=1500,
        dc_ac_ratio=1.20,
        strings_per_combiner=12,
        lat=51.0,
        pitch_m=6.5,
        mount_type="Single-Axis Tracker",
    )


def run_test_b() -> dict:
    layout = _synthetic_layout(15152, is_tracker=False, area_ha=80.0)
    return compute_electrical(
        layout=layout,
        module_name="LONGi Hi-MO 6 660Wp",
        inverter_name="Huawei SUN2000-196KTL (196 kW, 1500V)",
        system_voltage_v=1500,
        dc_ac_ratio=1.20,
        strings_per_combiner=12,
        lat=22.0,
        pitch_m=7.0,
        mount_type="Fixed Tilt",
    )


def _summary(label: str, result: dict) -> dict:
    s = result["string_sizing"]
    eb = result["electrical_bom"]
    dc_s = result["cables"]["dc_string_cable"]
    comb = result["cables"]["combiner"]
    return {
        "test": label,
        "modules_per_string": s["modules_per_string"],
        "total_strings": s["total_strings"],
        "n_inverters": s["n_inverters"],
        "dc_ac_ratio": s["dc_ac_ratio"],
        "Voc_max_string_V": s["Voc_max_string_V"],
        "Vmp_min_string_V": s["Vmp_min_string_V"],
        "valid": s["valid"],
        "dc_string_mm2": dc_s["size_mm2"],
        "dc_string_vdrop_pct": dc_s.get("vdrop_pct"),
        "combiners": comb["combiners_needed"],
        "inverter_type": s.get("inverter_type"),
        "warnings": s.get("warnings"),
    }


if __name__ == "__main__":
    a = _summary("A — DE SAT 14 MWp Jinko + Sungrow", run_test_a())
    b = _summary("B — IN FT 10 MWp LONGi + Huawei", run_test_b())
    print(json.dumps({"test_a": a, "test_b": b}, indent=2))
