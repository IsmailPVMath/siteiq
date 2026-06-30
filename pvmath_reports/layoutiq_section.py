"""LayoutIQ section for the unified PVMath PDF report."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import Spacer, Table, TableStyle

from pvmath_reports.common import ACCENT, BORDER, base_styles, lp, module_divider, section_hdr

_A3_BOM_KEYS = (
    "DC Capacity",
    "AC Capacity (est.)",
    "DC:AC Ratio",
    "Total Modules",
    "Total Strings",
    "Total tracker units",
    "Total Inverters",
    "Foundation Posts (est.)",
    "Rail / Purlin (m, est.)",
    "Module Clamps (est.)",
    "DC String Cable (est.)",
    "Site Area",
)


def build_layoutiq_flowables(
    layout_row: Optional[Dict[str, Any]] = None,
    *,
    bom: Optional[Dict[str, str]] = None,
    azimuth: float = 180.0,
    mount_type: str = "Fixed Tilt",
) -> List:
    """Tabular LayoutIQ summary — mirrors the A1 layout sheet sidebar."""
    if not layout_row:
        return []
    st = base_styles()
    story: List = [
        *module_divider(),
        section_hdr("LAYOUTIQ", st),
        Spacer(1, 0.15 * cm),
        lp(
            "Selected layout from the pitch sweep — same figures as the A1 layout sheet in the project package.",
            st["muted"],
        ),
        Spacer(1, 0.2 * cm),
    ]

    is_tracker = "Tracker" in str(layout_row.get("mount_type") or mount_type)
    mount_label = layout_row.get("label") or (
        "Single-Axis Tracker" if is_tracker else f"Fixed Tilt · Az {azimuth:g}°"
    )

    metrics = [
        [lp("Configuration", st["lbl"]), lp(str(layout_row.get("label") or "—"), st["body"])],
        [lp("Mounting", st["lbl"]), lp(str(mount_label), st["body"])],
        [lp("Pitch / GCR", st["lbl"]), lp(
            f"{layout_row.get('pitch_m', '—')} m · {layout_row.get('gcr', '—')}", st["body"]
        )],
        [lp("DC capacity", st["lbl"]), lp(
            f"{float(layout_row.get('dc_kwp') or 0):,.1f} kWp", st["body"]
        )],
        [lp("Modules", st["lbl"]), lp(f"{int(layout_row.get('total_modules') or 0):,}", st["body"])],
        [lp("Rows", st["lbl"]), lp(f"{int(layout_row.get('total_rows') or 0):,}", st["body"])],
        [lp("Site area", st["lbl"]), lp(f"{layout_row.get('area_ha', '—')} ha", st["body"])],
        [lp("Density", st["lbl"]), lp(
            f"{layout_row.get('mw_per_ha', '—')} MWp/ha"
            if layout_row.get("mw_per_ha") is not None
            else "—",
            st["body"],
        )],
    ]
    mt = Table(metrics, colWidths=[4.2 * cm, 12.8 * cm])
    mt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f5ee")),
        ("BOX", (0, 0), (-1, -1), 0.6, ACCENT),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(mt)

    bom_data = bom or layout_row.get("bom") or {}
    if isinstance(bom_data, dict) and bom_data:
        bom_rows = [[lp("Item", st["lbl"]), lp("Quantity", st["lbl"])]]
        for key in _A3_BOM_KEYS:
            if key in bom_data:
                bom_rows.append([lp(key, st["body"]), lp(str(bom_data[key]), st["body"])])
        if len(bom_rows) > 1:
            story.append(Spacer(1, 0.25 * cm))
            story.append(lp("Bill of materials (summary)", st["h3"]))
            story.append(Spacer(1, 0.08 * cm))
            bt = Table(bom_rows, colWidths=[10.5 * cm, 6.5 * cm])
            bt.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#145f34")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.5, ACCENT),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(bt)

    story.append(Spacer(1, 0.35 * cm))
    return story
