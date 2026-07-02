"""Preliminary BOM from layout results."""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

from layoutiq.tracker_units import tracker_unit_bom_lines
from layoutiq.electrical import electrical_to_bom_lines


def compute_bom(
    layout: dict,
    module_wp: int,
    n_portrait: int,
    modules_per_string: int,
    strings_per_inv: int,
    inv_ac_kw: float,
    target_dc_ac: float = 1.20,
    electrical: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    total_mod = layout["total_modules"]
    total_rows = layout["total_rows"]
    is_tracker = bool(layout.get("is_tracker"))
    dc_kwp = total_mod * module_wp / 1000

    total_strings = math.ceil(total_mod / modules_per_string) if total_mod else 0

    # Size inverters by power for a realistic DC:AC ratio (~1.2), not by an
    # arbitrary strings-per-inverter count. The old code used 4 strings per
    # 100 kW inverter which gave DC:AC ~0.6 and ~2x too many inverters.
    if inv_ac_kw and target_dc_ac:
        total_inv = max(1, round((dc_kwp / target_dc_ac) / inv_ac_kw)) if dc_kwp else 0
    else:
        total_inv = math.ceil(total_strings / strings_per_inv) if strings_per_inv else 0
    ac_kw = total_inv * inv_ac_kw
    dc_ac = round(dc_kwp / ac_kw, 3) if ac_kw else 0
    strings_per_inv_eff = max(1, round(total_strings / total_inv)) if total_inv else strings_per_inv

    # Foundation posts: along the torque tube (trackers) or per table leg line
    # (fixed). Tracker piles sit ~6 m apart; fixed-tilt posts ~5 m.
    post_spacing_m = 6.0 if is_tracker else 5.0
    total_posts = sum(
        max(2, math.ceil(r["length_m"] / post_spacing_m) + 1) for r in layout["rows_data"]
    )
    # Rail / purlin: a tracker carries modules on the torque tube (n_portrait
    # mounting lines); fixed-tilt tables need an extra purlin line.
    rails_lines = n_portrait if is_tracker else n_portrait + 1
    total_rail_m = round(sum(r["length_m"] * rails_lines for r in layout["rows_data"]))
    total_clamps = total_mod * 4
    dc_cable_m = total_mod * 10

    mw_per_ha = round(dc_kwp / 1000 / layout["area_ha"], 3) if layout["area_ha"] else 0
    mod_per_ha = round(total_mod / layout["area_ha"], 0) if layout["area_ha"] else 0

    bom = {
        "DC Capacity": f"{dc_kwp:,.1f} kWp",
        "AC Capacity (est.)": f"{ac_kw:,.0f} kW",
        "DC:AC Ratio": str(dc_ac),
        "Total Modules": f"{total_mod:,}",
        "Total Rows": str(total_rows),
        "Modules per String": str(modules_per_string),
        "Total Strings": f"{total_strings:,}",
        "Strings per Inverter": str(strings_per_inv_eff),
        "Total Inverters": f"{total_inv:,}",
        "Inverter AC (each)": f"{inv_ac_kw} kW",
        "Site Area": f"{layout['area_ha']} ha",
        "Land Use (DC)": f"{mw_per_ha} MWp/ha",
        "Modules / ha": f"{int(mod_per_ha):,}",
        "Foundation Posts (est.)": f"{total_posts:,}",
        "Rail / Purlin (m, est.)": f"{total_rail_m:,} m",
        "Module Clamps (est.)": f"{total_clamps:,}",
        "DC String Cable (est.)": f"{dc_cable_m:,} m",
    }
    unit_lines = tracker_unit_bom_lines(layout)
    if unit_lines:
        bom = {**bom, **unit_lines}
    if electrical:
        eb = electrical.get("electrical_bom") or {}
        if eb.get("modules_per_string"):
            bom["Modules per String"] = str(eb["modules_per_string"])
        if eb.get("total_strings"):
            bom["Total Strings"] = f"{int(eb['total_strings']):,}"
        if eb.get("inverter_count"):
            bom["Total Inverters"] = f"{int(eb['inverter_count']):,}"
        if eb.get("dc_ac_ratio"):
            bom["DC:AC Ratio"] = str(eb["dc_ac_ratio"])
        bom.update(electrical_to_bom_lines(electrical))
        bom["electrical"] = eb
    return bom
