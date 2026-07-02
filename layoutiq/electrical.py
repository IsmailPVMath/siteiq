"""LayoutIQ electrical screening — string sizing, cables, combiners, BOM."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from layoutiq.cable_calc import compute_cable_bom
from layoutiq.equipment_db import get_inverter, get_module
from layoutiq.string_calc import compute_string_sizing


def compute_electrical(
    *,
    layout: Dict[str, Any],
    module_name: str,
    inverter_name: str,
    system_voltage_v: int = 1500,
    dc_ac_ratio: float = 1.20,
    strings_per_combiner: int = 12,
    lat: Optional[float] = None,
    tmy_t2m: Optional[List[float]] = None,
    pitch_m: float = 6.0,
    module_override: Optional[Dict[str, Any]] = None,
    inverter_override: Optional[Dict[str, Any]] = None,
    ac_run_m: float = 50.0,
    lv_voltage_v: float = 400.0,
    mount_type: str = "",
) -> Dict[str, Any]:
    module = dict(module_override or get_module(module_name))
    inverter = dict(inverter_override or get_inverter(inverter_name))

    total_modules = int(layout.get("total_modules") or 0)
    module_wp = int(module.get("Wp") or 550)
    dc_kwp = total_modules * module_wp / 1000.0
    is_tracker = bool(layout.get("is_tracker")) or "tracker" in mount_type.lower() or mount_type.upper().startswith("SAT")

    string = compute_string_sizing(
        total_modules=total_modules,
        dc_kwp=dc_kwp,
        module=module,
        inverter=inverter,
        module_name=module_name,
        inverter_name=inverter_name,
        system_voltage_v=system_voltage_v,
        dc_ac_ratio=dc_ac_ratio,
        lat=lat,
        tmy_t2m=tmy_t2m,
        is_tracker=is_tracker,
    )

    cables = compute_cable_bom(
        string_sizing=string,
        module=module,
        inverter=inverter,
        layout=layout,
        pitch_m=pitch_m,
        area_ha=float(layout.get("area_ha") or 1.0),
        strings_per_combiner=strings_per_combiner,
        ac_run_m=ac_run_m,
        lv_voltage_v=lv_voltage_v,
    )

    dc_string = cables["dc_string_cable"]
    dc_main = cables.get("dc_main_cable")
    ac_lv = cables["ac_lv_cable"]
    combiner = cables["combiner"]

    electrical_bom = {
        "module_model": module_name,
        "inverter_model": inverter_name,
        "inverter_count": string["n_inverters"],
        "system_voltage_V": string["system_voltage_V"],
        "modules_per_string": string["modules_per_string"],
        "total_strings": string["total_strings"],
        "dc_ac_ratio": string["dc_ac_ratio"],
        "dc_string_cable_mm2": dc_string["size_mm2"],
        "dc_string_cable_m": dc_string.get("total_length_m"),
        "dc_main_cable_mm2": dc_main["size_mm2"] if dc_main else None,
        "dc_main_cable_m": dc_main.get("total_length_m") if dc_main else None,
        "ac_lv_cable_mm2": ac_lv["size_mm2"],
        "ac_lv_cable_m": ac_lv.get("total_length_m"),
        "string_combiners": combiner["combiners_needed"],
        "Voc_max_string_V": string["Voc_max_string_V"],
        "Vmp_op_string_V": string["Vmp_op_string_V"],
        "voc_margin_pct": string.get("voc_margin_pct"),
        "voc_margin_low": string.get("voc_margin_low"),
    }

    return {
        "string_sizing": string,
        "cables": cables,
        "electrical_bom": electrical_bom,
        "disclaimer": (
            "Indicative electrical screening only — not for construction, permitting, "
            "or protection coordination. Verify with a certified electrical engineer."
        ),
    }


def electrical_to_bom_lines(electrical: Dict[str, Any]) -> Dict[str, str]:
    """Merge electrical quantities into display BOM strings."""
    eb = electrical.get("electrical_bom") or {}
    comb = (electrical.get("cables") or {}).get("combiner") or {}
    lines: Dict[str, str] = {
        "Module (electrical)": str(eb.get("module_model", "—")),
        "Inverter (electrical)": str(eb.get("inverter_model", "—")),
        "Modules / String (calc)": str(eb.get("modules_per_string", "—")),
        "String Voc max": f"{eb.get('Voc_max_string_V', '—')} V",
        "Voc margin (cold)": f"{eb.get('voc_margin_pct', '—')}%",
        "String Vmp nom.": f"{eb.get('Vmp_op_string_V', '—')} V",
        "DC String Cable": f"{eb.get('dc_string_cable_mm2', '—')} mm² · {eb.get('dc_string_cable_m', '—')} m",
        "AC LV Cable": f"{eb.get('ac_lv_cable_mm2', '—')} mm² · {eb.get('ac_lv_cable_m', '—')} m",
    }
    if eb.get("dc_main_cable_mm2"):
        lines["DC Main Cable"] = f"{eb['dc_main_cable_mm2']} mm² · {eb.get('dc_main_cable_m', '—')} m"
    if comb.get("combiners_needed"):
        lines["String Combiners"] = f"{comb['combiners_needed']} units"
    return lines
