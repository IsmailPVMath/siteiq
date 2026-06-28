"""SiteIQ PDF section for the unified PVMath report."""

from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, Spacer, Table, TableStyle

from pvmath_pdf import strip_pdf_label
from pvmath_reports.common import (
    ACCENT,
    BORDER,
    DARK,
    LGRAY,
    MUTED,
    base_styles,
    lp,
    section_hdr,
)
from pvmath_reports.siteiq_next_steps import get_next_steps
from pvmath_reports.siteiq_suitability import SUITABILITY_WEIGHTS, compute_site_suitability

_MONTH_COLORS = [
    "#f87171", "#fb923c", "#facc15", "#a3e635", "#4ade80", "#22c55e",
    "#22c55e", "#4ade80", "#a3e635", "#facc15", "#fb923c", "#f87171",
]


def _terrain_from_topo(topo: Optional[Dict[str, Any]], mount_type: str) -> tuple[dict, str]:
    if not topo:
        return {"success": False}, "— (TerrainIQ not run)"
    slope = topo.get("slope") or {}
    vf = topo.get("verdict_fixed") or {}
    vt = topo.get("verdict_tracker") or {}
    label = vt.get("label", "—") if mount_type == "Single-Axis Tracker" else vf.get("label", "—")
    terrain = {
        "success": True,
        "terrainiq_confirmed": True,
        "topoiq_confirmed": True,
        "mean_slope_pct": slope.get("mean"),
        "max_slope_pct": slope.get("max"),
    }
    return terrain, str(label or "—")


def _monthly_irradiation_chart(monthly_ghi: List[float]) -> Optional[Drawing]:
    if not monthly_ghi:
        return None
    ghi_vals = [float(v) for v in monthly_ghi[:12]]
    if not ghi_vals:
        return None
    months_abbr = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    max_ghi = max(ghi_vals) or 1.0
    chart_w = 17 * cm
    chart_h = 5 * cm
    pad_l, pad_b, pad_r, pad_t = 1.2 * cm, 1.2 * cm, 0.3 * cm, 0.3 * cm
    n = len(ghi_vals)
    bar_area_w = chart_w - pad_l - pad_r
    bar_area_h = chart_h - pad_b - pad_t
    bar_w = bar_area_w / n * 0.62
    gap = bar_area_w / n

    d = Drawing(chart_w, chart_h)
    for gi, gv in enumerate([0.25, 0.5, 0.75, 1.0]):
        gy = pad_b + bar_area_h * gv
        d.add(Line(pad_l, gy, chart_w - pad_r, gy, strokeColor=colors.HexColor("#d4e0d4"), strokeWidth=0.5))
        d.add(String(pad_l - 4, gy - 3, str(int(max_ghi * gv)), fontSize=6, fillColor=MUTED, textAnchor="end"))

    for i, (m, v) in enumerate(zip(months_abbr, ghi_vals)):
        ratio = v / max_ghi
        bh = bar_area_h * ratio
        bx = pad_l + i * gap + (gap - bar_w) / 2
        d.add(Rect(bx, pad_b, bar_w, bh, fillColor=colors.HexColor(_MONTH_COLORS[i % 12]), strokeColor=None))
        d.add(String(bx + bar_w / 2, pad_b - 10, m, fontSize=7, fillColor=DARK, textAnchor="middle"))
        if bh > 10:
            d.add(String(bx + bar_w / 2, pad_b + bh + 2, str(int(v)), fontSize=6.5, fillColor=DARK, textAnchor="middle"))

    d.add(Line(pad_l, pad_b, chart_w - pad_r, pad_b, strokeColor=colors.HexColor("#d4e0d4"), strokeWidth=1))
    return d


def build_siteiq_flowables(
    *,
    screening: Dict[str, Any],
    topo: Optional[Dict[str, Any]],
    score: Optional[Dict[str, Any]],
    country: str,
    land_use: str,
    mount_type: str,
    lat: float,
    lon: float,
) -> List:
    st = base_styles()
    story: List = []

    scr = screening or {}
    solar = scr.get("solar") or {}
    flood = scr.get("flood") or {}
    reg = scr.get("regulatory") or {}
    cap = scr.get("capacity") or {}

    solar_lbl = str(solar.get("rating") or "—")
    flood_risk = str(flood.get("risk") or "—")
    eeg_status = str(reg.get("status") or "—")

    terrain, slope_lbl = _terrain_from_topo(topo, mount_type)
    cap_for_suit = None
    if cap.get("mwp_range"):
        cap_for_suit = {"mwp_lo": 0, "mwp_hi": 0}

    suit = compute_site_suitability(
        solar_lbl, slope_lbl, flood_risk, land_use, solar, terrain,
        mount_type=mount_type, country=country, eeg_status=eeg_status,
        project_country=country, cap=cap_for_suit,
    )

    pvm_score = (score or {}).get("pvmath_score") if score else None
    verdict_label = (score or {}).get("verdict") or suit["verdict_label"]
    verdict_txt = (score or {}).get("verdict_detail") or (
        f"Weighted screening score {suit['overall']}/100 across solar, terrain, flood, land, and regulatory factors."
    )

    story.append(PageBreak())
    story.append(section_hdr("SiteIQ — Site screening", st))
    story.append(Spacer(1, 0.2 * cm))

    _is_positive = any(x in str(verdict_label).upper() for x in ("EXCELLENT", "VERY GOOD", "GOOD"))
    _is_acc = "ACCEPTABLE" in str(verdict_label).upper() or "CHALLENGING" in str(verdict_label).upper()
    v_color = ACCENT if _is_positive else (colors.HexColor("#f59e0b") if _is_acc else colors.HexColor("#dc2626"))
    v_bg = colors.HexColor("#e8f5ee") if _is_positive else (
        colors.HexColor("#fef9c3") if _is_acc else colors.HexColor("#fee2e2")
    )

    story.append(section_hdr("OVERALL VERDICT", st))
    story.append(Spacer(1, 0.12 * cm))
    vt = Table([[
        Paragraph(
            f"<b>{strip_pdf_label(str(verdict_label))}</b>",
            ParagraphStyle("V", fontSize=13, fontName="Helvetica-Bold", textColor=v_color, leading=16),
        ),
        lp(verdict_txt, st["body"]),
    ]], colWidths=[6.5 * cm, 10.5 * cm])
    vt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), v_bg),
        ("BOX", (0, 0), (-1, -1), 1.5, v_color),
        ("TOPPADDING", (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(vt)
    story.append(Spacer(1, 0.3 * cm))

    story.append(section_hdr("SITE SUITABILITY BREAKDOWN", st))
    story.append(Spacer(1, 0.12 * cm))
    display_score = pvm_score if pvm_score is not None else suit["overall"]
    story.append(Paragraph(
        f"<b>Overall Score: {display_score}/100 "
        f"(<font color='#1d9e52'>{verdict_label}</font>)</b>",
        ParagraphStyle("OvScore", fontSize=11, fontName="Helvetica-Bold", textColor=DARK, leading=15),
    ))
    story.append(Spacer(1, 0.12 * cm))

    brk_rows = [[lp("Category", st["white"]), lp("Score", st["white"]), lp("Weight", st["white"])]]
    for label, key, weight in SUITABILITY_WEIGHTS:
        brk_rows.append([lp(label, st["body"]), lp(str(suit["scores"][key]), st["body"]), lp(f"{weight}%", st["muted"])])
    brk_t = Table(brk_rows, colWidths=[8.5 * cm, 4 * cm, 4.5 * cm])
    brk_t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LGRAY]),
    ]))
    story.append(brk_t)
    story.append(Spacer(1, 0.3 * cm))

    story.append(section_hdr("KEY DRIVERS", st))
    story.append(Spacer(1, 0.1 * cm))
    for kind, text in suit["drivers"]:
        icon_col = "#1d9e52" if kind == "positive" else "#e85d04"
        icon = "+" if kind == "positive" else "!"
        story.append(Paragraph(
            f'<font color="{icon_col}"><b>{icon}</b></font>&nbsp;&nbsp;{text}',
            ParagraphStyle("Kd", fontSize=8.5, textColor=DARK, leading=12),
        ))
        story.append(Spacer(1, 0.08 * cm))
    story.append(Spacer(1, 0.25 * cm))

    monthly_ghi = solar.get("monthly_ghi") or []
    chart = _monthly_irradiation_chart(monthly_ghi)
    if chart:
        story.append(section_hdr("MONTHLY SOLAR IRRADIATION (kWh/m²)", st))
        story.append(Spacer(1, 0.12 * cm))
        peak_i = monthly_ghi.index(max(monthly_ghi)) if monthly_ghi else 0
        months_abbr = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        sub = lp(
            f"Peak month: {months_abbr[peak_i]} ({max(monthly_ghi):.0f} kWh/m²)  |  "
            f"Annual total: {sum(monthly_ghi):.0f} kWh/m²",
            st["muted"],
        )
        story.append(KeepTogether([chart, Spacer(1, 0.15 * cm), sub]))
        story.append(Spacer(1, 0.35 * cm))

    story.append(section_hdr("RECOMMENDED NEXT STEPS", st))
    story.append(Spacer(1, 0.12 * cm))
    for step in get_next_steps(country, land_use, lat=lat, lon=lon):
        story.append(lp(step, st["body"]))
        story.append(Spacer(1, 0.12 * cm))

    return story
