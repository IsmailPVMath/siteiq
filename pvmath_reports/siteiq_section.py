"""SiteIQ PDF section for the unified PVMath report."""

from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

from pvmath_geocode import pdf_escape
from pvmath_pdf import strip_pdf_label
from pvmath_reports.common import (
    ACCENT,
    BORDER,
    DARK,
    LGRAY,
    MUTED,
    base_styles,
    lp,
    module_divider,
    section_hdr,
)
from pvmath_reports.siteiq_next_steps import get_next_steps

_MONTH_COLORS = ["#1d9e52"] * 12


def _rating_color(rating: str):
    """Map a screening rating to the PVMath traffic-light palette."""
    r = (rating or "").strip().upper()
    if any(x in r for x in ("EXCELLENT", "VERY GOOD", "GOOD", "LOW")):
        return ACCENT
    if any(x in r for x in ("MODERATE", "ACCEPTABLE", "CHALLENGING", "FAIR")):
        return colors.HexColor("#f59e0b")
    if any(x in r for x in ("HIGH", "CRITICAL", "POOR", "REMOTE")):
        return colors.HexColor("#dc2626")
    return MUTED


def _screen_card(st, label: str, rating: str, detail: str, sub: str) -> Table:
    """One screening metric tile: muted label, coloured rating, detail, sub-line."""
    color = _rating_color(rating)
    lbl_s = ParagraphStyle("crd_lbl", fontSize=7, fontName="Helvetica-Bold",
                           textColor=MUTED, leading=9, spaceAfter=3)
    rat_s = ParagraphStyle("crd_rat", fontSize=12.5, fontName="Helvetica-Bold",
                           textColor=color, leading=15, spaceAfter=2)
    det_s = ParagraphStyle("crd_det", fontSize=8, textColor=DARK, leading=10.5)
    sub_s = ParagraphStyle("crd_sub", fontSize=7.5, textColor=MUTED, leading=9.5, spaceBefore=2)

    inner = [
        [Paragraph(pdf_escape(strip_pdf_label(str(label)).upper()), lbl_s)],
        [Paragraph(f"<b>{pdf_escape(strip_pdf_label(str(rating)) or '—')}</b>", rat_s)],
    ]
    det = strip_pdf_label(str(detail or "")).strip()
    if det:
        inner.append([Paragraph(pdf_escape(det), det_s)])
    sub = str(sub or "").strip()
    if sub:
        inner.append([Paragraph(pdf_escape(sub), sub_s)])

    card = Table(inner, colWidths=[8.0 * cm])
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, color),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (0, 0), 9),
        ("BOTTOMPADDING", (0, -1), (0, -1), 9),
    ]))
    return card


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
    grid = scr.get("grid") or {}

    solar_lbl = str(solar.get("rating") or "—")
    flood_risk = str(flood.get("risk") or "—")
    eeg_status = str(reg.get("status") or "—")

    story.extend(module_divider())
    story.append(section_hdr("SiteIQ — Site screening", st))
    story.append(Spacer(1, 0.2 * cm))

    # Representative screening snapshot — solar resource, flood, grid proximity
    # (OpenStreetMap) and regulatory / tariff applicability. Capacity is no longer
    # estimated here; it is computed per mount type in LayoutIQ.
    solar_sub = (
        f"{solar.get('annual_ghi')} kWh/m\u00b2/yr"
        if solar.get("annual_ghi") not in (None, "")
        else ""
    )

    nearest = grid.get("nearest") or {}
    if grid.get("found") and nearest:
        grid_sub = f"{nearest.get('name') or 'Substation'} \u00b7 {grid.get('distance_km')} km"
        if nearest.get("voltage"):
            grid_sub += f" \u00b7 {nearest['voltage']}"
    elif grid.get("found") is False:
        grid_sub = f"No OSM substation within {grid.get('search_radius_km') or '?'} km"
    else:
        grid_sub = ""

    cards = [
        _screen_card(st, "Solar", solar_lbl, str(solar.get("detail") or ""), solar_sub),
        _screen_card(st, "Flood", flood_risk, str(flood.get("detail") or ""), ""),
        _screen_card(st, "Grid proximity", str(grid.get("rating") or "—"),
                     str(grid.get("detail") or ""), grid_sub),
        _screen_card(st, "Regulatory", eeg_status, str(reg.get("note") or ""), ""),
    ]
    card_grid = Table(
        [[cards[0], cards[1]], [cards[2], cards[3]]],
        colWidths=[8.5 * cm, 8.5 * cm],
    )
    card_grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 0),
    ]))
    story.append(card_grid)
    story.append(Spacer(1, 0.2 * cm))

    if grid.get("disclaimer"):
        story.append(lp(str(grid["disclaimer"]), st["muted"]))
    story.append(lp(
        "Capacity is computed per mount type in LayoutIQ (portrait orientation, GCR) "
        "— not estimated at screening.",
        st["muted"],
    ))
    story.append(Spacer(1, 0.3 * cm))

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
