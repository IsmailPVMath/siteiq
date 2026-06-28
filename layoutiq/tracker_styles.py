"""Tracker unit colors — 8S through 1S (PVMath / CAD / A3 legend)."""

from __future__ import annotations

from typing import Any, Dict

# Predefined fill/stroke for web map, matplotlib, and DXF ACI color index.
# NOTE: green and red are intentionally avoided here — they are reserved for the
# upcoming internal vs external string distinction. Palette uses blues, cyan,
# indigo, amber, orange, magenta, and purple only.
TRACKER_UNIT_STYLES: Dict[int, Dict[str, Any]] = {
    8: {"label": "8S", "fill": "#1e3a8a", "stroke": "#172554", "dxf_color": 5, "dxf_layer": "PV_8S"},
    7: {"label": "7S", "fill": "#2563eb", "stroke": "#1e40af", "dxf_color": 150, "dxf_layer": "PV_7S"},
    6: {"label": "6S", "fill": "#0891b2", "stroke": "#0e7490", "dxf_color": 4, "dxf_layer": "PV_6S"},
    5: {"label": "5S", "fill": "#4f46e5", "stroke": "#4338ca", "dxf_color": 170, "dxf_layer": "PV_5S"},
    4: {"label": "4S", "fill": "#ca8a04", "stroke": "#a16207", "dxf_color": 2, "dxf_layer": "PV_4S"},
    3: {"label": "3S", "fill": "#ea580c", "stroke": "#c2410c", "dxf_color": 30, "dxf_layer": "PV_3S"},
    2: {"label": "2S", "fill": "#db2777", "stroke": "#be185d", "dxf_color": 230, "dxf_layer": "PV_2S"},
    1: {"label": "1S", "fill": "#9333ea", "stroke": "#7e22ce", "dxf_color": 200, "dxf_layer": "PV_1S"},
}

DEFAULT_TRACKER_OPTIONS = [8, 7, 6, 5, 4, 3, 2, 1]


def style_for_unit(unit_strings: int) -> Dict[str, Any]:
    return TRACKER_UNIT_STYLES.get(
        int(unit_strings),
        {
            "label": f"{int(unit_strings)}S",
            "fill": "#64748b",
            "stroke": "#475569",
            "dxf_color": 8,
            "dxf_layer": f"PV_{int(unit_strings)}S",
        },
    )
