"""Indicative single-line diagram as SVG (screening grade)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional


def build_sld_svg(
    *,
    electrical: Dict[str, Any],
    dc_kwp: float,
    total_modules: int,
    grid_voltage_kv: float = 20.0,
) -> str:
    string = electrical.get("string_sizing") or {}
    cables = electrical.get("cables") or {}
    combiner = cables.get("combiner") or {}
    inv_type = string.get("inverter_type", "string")
    n_inv = int(string.get("n_inverters") or 1)
    paco = string.get("inverter_model", "Inverter")
    module = string.get("module_model", "Module")

    root = ET.Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        width="900",
        height="500",
        viewBox="0 0 900 500",
    )
    ET.SubElement(root, "rect", width="900", height="500", fill="#f5f7f5")

    def box(x, y, w, h, fill, stroke, label, sub=""):
        ET.SubElement(root, "rect", x=str(x), y=str(y), width=str(w), height=str(h), fill=fill, stroke=stroke, **{"stroke-width": "2"})
        t = ET.SubElement(root, "text", x=str(x + w / 2), y=str(y + h / 2 - 6), **{"text-anchor": "middle", "font-family": "Inter,Arial,sans-serif", "font-size": "13", "font-weight": "700", "fill": "#1a2e1a"})
        t.text = label
        if sub:
            t2 = ET.SubElement(root, "text", x=str(x + w / 2), y=str(y + h / 2 + 14), **{"text-anchor": "middle", "font-family": "Inter,Arial,sans-serif", "font-size": "11", "fill": "#3a5a3a"})
            t2.text = sub

    def arrow(x1, y1, x2, y2, color="#666"):
        ET.SubElement(root, "line", x1=str(x1), y1=str(y1), x2=str(x2), y2=str(y2), stroke=color, **{"stroke-width": "2", "marker-end": "url(#arr)"})
        defs = root.find("defs")
        if defs is None:
            defs = ET.SubElement(root, "defs")
            m = ET.SubElement(defs, "marker", id="arr", markerWidth="8", markerHeight="8", refX="6", refY="3", orient="auto")
            ET.SubElement(m, "path", d="M0,0 L6,3 L0,6 Z", fill=color)

    y = 200
    box(20, y, 140, 70, "#e8f5ee", "#1d9e52", "PV Array", f"{dc_kwp:,.0f} kWp DC\n{total_modules:,} mod")
    x = 180

    if inv_type == "central" and combiner.get("combiners_needed"):
        box(x, y, 120, 70, "#fff8ef", "#d4840a", "Combiners", f"{combiner['combiners_needed']} × 1500V")
        arrow(160, y + 35, x, y + 35, "#d4840a")
        x += 150
        arrow(x - 30, y + 35, x, y + 35, "#d4840a")

    inv_label = "Central INV" if inv_type == "central" else "String INV"
    box(x, y, 150, 70, "#eef2ee", "#5a7a5a", inv_label, f"{n_inv} × {paco[:24]}")
    arrow(x - 30 if x > 180 else 160, y + 35, x, y + 35, "#1d9e52" if x == 180 else "#666")
    x += 170

    box(x, y, 100, 70, "#eef2ee", "#5a7a5a", "AC Bus", "400V AC")
    arrow(x - 20, y + 35, x, y + 35, "#c0392b")
    x += 120

    kva = int(n_inv * 196 * 1.05) if inv_type == "string" else int(dc_kwp / max(string.get("dc_ac_ratio") or 1.2, 0.1))
    box(x, y, 120, 70, "#eef2ee", "#5a7a5a", "MV XFMR", f"{kva:,} kVA\n400V/{grid_voltage_kv:.0f}kV")
    arrow(x - 20, y + 35, x, y + 35, "#c0392b")
    x += 140

    box(x, y, 120, 70, "#e8f5ee", "#1d9e52", "Grid POI", f"{grid_voltage_kv:.0f} kV")
    arrow(x - 20, y + 35, x, y + 35, "#1d9e52")

    title = ET.SubElement(root, "text", x="450", y="40", **{"text-anchor": "middle", "font-family": "Inter,Arial,sans-serif", "font-size": "16", "font-weight": "800", "fill": "#145f34"})
    title.text = "System SLD — Indicative (Screening Grade)"
    sub = ET.SubElement(root, "text", x="450", y="62", **{"text-anchor": "middle", "font-family": "Inter,Arial,sans-serif", "font-size": "11", "fill": "#5a7a5a"})
    sub.text = f"Module: {module[:40]} · Not for construction or permitting"

    return ET.tostring(root, encoding="unicode")
