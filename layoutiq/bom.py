"""Preliminary BOM from layout results."""

from __future__ import annotations

import math

from layoutiq.tracker_units import tracker_unit_bom_lines


def compute_bom(
    layout: dict,
    module_wp: int,
    n_portrait: int,
    modules_per_string: int,
    strings_per_inv: int,
    inv_ac_kw: float,
) -> dict[str, str]:
    total_mod = layout["total_modules"]
    total_rows = layout["total_rows"]
    dc_kwp = total_mod * module_wp / 1000

    total_strings = math.ceil(total_mod / modules_per_string)
    total_inv = math.ceil(total_strings / strings_per_inv)
    ac_kw = total_inv * inv_ac_kw
    dc_ac = round(dc_kwp / ac_kw, 3) if ac_kw else 0

    total_posts = sum(
        max(2, math.ceil(r["length_m"] / 4) + 1) for r in layout["rows_data"]
    )
    rails_lines = n_portrait + 1
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
        "Strings per Inverter": str(strings_per_inv),
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
    return bom
