"""Unified PVMath project intelligence PDF — SiteIQ + TerrainIQ + YieldIQ."""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from pvmath_brand import PRODUCT_NAME
from pvmath_geocode import format_coords, resolve_location_label
from pvmath_pdf import SITEIQ_DISCLAIMER_BODY, append_siteiq_metrics_annexure
from pvmath_reports.common import ACCENT, ACCENT_HDR, BORDER, DARK, MUTED, base_styles, lp, module_banner, module_divider, section_hdr
from pvmath_reports.layoutiq_section import build_layoutiq_flowables
from pvmath_reports.siteiq_section import build_siteiq_flowables
from pvmath_reports.terrain_section import build_terrain_section_flowables
from pvmath_reports.yieldiq_section import build_yieldiq_flowables
from pvmath_terrain_report import FIXED_THRESHOLDS, TRACKER_THRESHOLDS
from pvmath_workflow.mount_utils import resolve_mount_type, yield_config_key_from_layout_row
from pvmath_workflow.score_config import SUITABILITY_WEIGHTS, SUITABILITY_WEIGHTS_PARTIAL
from pvmath_workflow.scoring import unified_pvmath_score, yield_subscore

_FOOTER_GREY = colors.HexColor("#8a9a8a")
_FOOTER_RULE = colors.HexColor("#d4e8d4")


class _NumberedCanvas(_canvas.Canvas):
    """Two-pass canvas that stamps a clean footer with 'Page X/N' on every page."""

    _footer_date = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_states: list = []

    def showPage(self):
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_states)
        for index, state in enumerate(self._saved_states, start=1):
            self.__dict__.update(state)
            self._draw_footer(index, total)
            super().showPage()
        super().save()

    def _draw_footer(self, page_number: int, total_pages: int):
        width, _ = A4
        margin = 1.8 * cm
        y = 1.05 * cm
        self.saveState()
        self.setStrokeColor(_FOOTER_RULE)
        self.setLineWidth(0.5)
        self.line(margin, y + 0.32 * cm, width - margin, y + 0.32 * cm)
        self.setFillColor(_FOOTER_GREY)
        if self._footer_date:
            self.setFont("Helvetica", 7.5)
            self.drawString(margin, y, self._footer_date)
        self.setFont("Helvetica-Bold", 7.5)
        self.drawCentredString(width / 2.0, y, PRODUCT_NAME)
        self.setFont("Helvetica", 7.5)
        self.drawRightString(width - margin, y, f"Page {page_number}/{total_pages}")
        self.restoreState()


def _project_summary_flowables(
    *,
    project_name: str,
    country: str,
    location_label: str,
    lat: Optional[float],
    lon: Optional[float],
    land_use: str,
    mount_type: str,
    area_ha: float,
    layout_dc_kwp: Optional[float] = None,
) -> List:
    st = base_styles()
    loc_line = location_label or (
        resolve_location_label(lat, lon, country=country) if lat is not None and lon is not None else "—"
    )
    coord = format_coords(lat, lon) if lat is not None and lon is not None else "—"

    rows = [
        [lp("Project", st["lbl"]), lp(project_name or "—", st["body"])],
        [lp("Location", st["lbl"]), lp(loc_line, st["body"])],
        [lp("Coordinates", st["lbl"]), lp(coord, st["body"])],
        [lp("Site area", st["lbl"]), lp(f"{area_ha:,.1f} ha" if area_ha else "—", st["body"])],
        [lp("Land use", st["lbl"]), lp(land_use or "—", st["body"])],
        [lp("Mounting", st["lbl"]), lp(mount_type or "—", st["body"])],
    ]
    try:
        dc = float(layout_dc_kwp) if layout_dc_kwp is not None else 0.0
    except (TypeError, ValueError):
        dc = 0.0
    if dc > 0:
        mwp = dc / 1000.0
        cap_txt = f"~{mwp:.0f} MWp DC" if mwp >= 100 else f"~{mwp:.1f} MWp DC"
        rows.append([lp("Capacity from LayoutIQ", st["lbl"]), lp(cap_txt, st["body"])])
    rows.append([lp("Generated", st["lbl"]), lp(datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), st["body"])])
    tbl = Table(rows, colWidths=[4.2 * cm, 12.8 * cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f5ee")),
        ("BOX", (0, 0), (-1, -1), 0.6, ACCENT),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return [
        module_banner(
            "PVMath — Project Intelligence Report",
            "SiteIQ · TerrainIQ · LayoutIQ · YieldIQ",
            st,
        ),
        Spacer(1, 0.35 * cm),
        section_hdr("PROJECT SUMMARY", st),
        Spacer(1, 0.15 * cm),
        tbl,
        Spacer(1, 0.4 * cm),
    ]


def _verdict_palette(verdict: str):
    v = (verdict or "").upper()
    if any(x in v for x in ("EXCELLENT", "VERY GOOD", "GOOD")):
        return ACCENT, colors.HexColor("#e8f5ee")
    if "ACCEPTABLE" in v or "MODERATE" in v or "CHALLENGING" in v:
        return colors.HexColor("#f59e0b"), colors.HexColor("#fef9c3")
    return colors.HexColor("#dc2626"), colors.HexColor("#fee2e2")


def _pvmath_score_flowables(result: Dict[str, Any]) -> List:
    """Final aggregate PVMath score — placed last, after all module sections."""
    st = base_styles()
    overall = result.get("pvmath_score")
    verdict = str(result.get("verdict") or "")
    components = result.get("components") or {}
    viability = result.get("viability") or {}
    score_mode = result.get("score_mode") or viability.get("score_mode") or "partial"
    v_color, v_bg = _verdict_palette(verdict)

    mode_note = (
        "Full composite includes YieldIQ energy yield (regional benchmark)."
        if score_mode == "full"
        else "Partial composite — energy yield pending YieldIQ."
    )

    story: List = [
        *module_divider(),
        section_hdr("PVMATH SITE RATING", st),
        Spacer(1, 0.15 * cm),
        lp(
            f"{mode_note} Terrain caps the score on challenging sites. "
            "DC capacity is from LayoutIQ.",
            st["muted"],
        ),
        Spacer(1, 0.2 * cm),
    ]

    big = Table([[
        Paragraph(
            f"<b>{overall if overall is not None else '—'}/100</b>",
            ParagraphStyle("bigscore", fontSize=30, fontName="Helvetica-Bold",
                           textColor=v_color, leading=34),
        ),
        Paragraph(
            f"<b>{verdict or '—'}</b><br/>"
            f"<font size='9'>{viability.get('engineering_confidence_stars', '')} "
            f"{viability.get('engineering_confidence', '')}</font>",
            ParagraphStyle("bigverdict", fontSize=15, fontName="Helvetica-Bold",
                           textColor=v_color, leading=19),
        ),
    ]], colWidths=[5 * cm, 12 * cm])
    big.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), v_bg),
        ("BOX", (0, 0), (-1, -1), 1.5, v_color),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(big)
    story.append(Spacer(1, 0.25 * cm))

    if viability:
        econ_rows = [
            [lp("Qualitative rating", st["lbl"]), lp(str(viability.get("qualitative_rating") or verdict), st["body"])],
            [lp("Engineering confidence", st["lbl"]), lp(
                f"{viability.get('engineering_confidence_stars', '')} "
                f"{viability.get('engineering_confidence', '—')}",
                st["body"],
            )],
            [lp("Investment risk", st["lbl"]), lp(str(viability.get("investment_risk") or "—"), st["body"])],
            [lp("Utility-scale PV recommended", st["lbl"]), lp(
                str(viability.get("utility_scale_recommended") or "—"), st["body"],
            )],
        ]
        econ = Table(econ_rows, colWidths=[6.5 * cm, 10.5 * cm])
        econ.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f5ee")),
            ("BOX", (0, 0), (-1, -1), 0.6, ACCENT),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(econ)
        story.append(Spacer(1, 0.25 * cm))

    rows = [[lp("Factor", st["white"]), lp("Score", st["white"]), lp("Weight", st["white"])]]
    weight_rows = SUITABILITY_WEIGHTS if score_mode == "full" else SUITABILITY_WEIGHTS_PARTIAL
    for label, key, weight in weight_rows:
        val = components.get(key)
        if val is None and key == "yield":
            continue
        rows.append([
            lp(label, st["body"]),
            lp(f"{int(val)}/100" if val is not None else "—", st["body"]),
            lp(f"{weight}%", st["body"]),
        ])
    bt = Table(rows, colWidths=[8.5 * cm, 4 * cm, 4.5 * cm])
    bt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7f5")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(bt)
    story.append(Spacer(1, 0.35 * cm))
    return story


def _annex_flowables() -> List:
    st = base_styles()
    story: List = [
        *module_divider(),
        section_hdr("DISCLAIMERS & REFERENCE", st),
        Spacer(1, 0.2 * cm),
        lp(SITEIQ_DISCLAIMER_BODY, st["muted"]),
        Spacer(1, 0.35 * cm),
    ]
    append_siteiq_metrics_annexure(
        story,
        accent_color="#1d9e52",
        muted_color="#5a7a5a",
        border_color="#d4e8d4",
        dark_color="#1a2e1a",
        exclude=("Est. DC Capacity", "Est. Output"),
    )
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph(
        "<b>Verdict scale:</b> Excellent &gt; Very Good &gt; Good &gt; Acceptable &gt; Challenging &gt; Critical",
        ParagraphStyle("vscale", parent=st["muted"], fontSize=8, leading=11),
    ))
    story.append(Spacer(1, 0.2 * cm))
    for title, rows in (("Fixed Tilt slope thresholds", FIXED_THRESHOLDS), ("Tracker slope thresholds", TRACKER_THRESHOLDS)):
        story.append(lp(title, st["h3"]))
        data = [["Rating", "Threshold", "Interpretation"]] + [list(r) for r in rows]
        t = Table(data, colWidths=[3.5 * cm, 3 * cm, 10.5 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), ACCENT_HDR),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.15 * cm))
    story += [
        Spacer(1, 0.3 * cm),
        HRFlowable(width="100%", thickness=0.5, color=BORDER),
        Spacer(1, 0.2 * cm),
        lp(
            f"Generated by {PRODUCT_NAME} | For professional use only. "
            "Data: PVGIS (JRC), routed public DEM, OpenStreetMap.",
            st["muted"],
        ),
    ]
    return story


def build_unified_pvmath_report_pdf(
    *,
    project_name: str,
    country: str = "",
    lat: float | None = None,
    lon: float | None = None,
    land_use: str = "Standard",
    mount_type: str = "Fixed Tilt",
    area_ha: float = 0.0,
    location_label: str = "",
    screening: Optional[Dict[str, Any]] = None,
    topo: Optional[Dict[str, Any]] = None,
    score: Optional[Dict[str, Any]] = None,
    yield_result: Optional[Dict[str, Any]] = None,
    selected_config_key: Optional[str] = None,
    selected_dc_kwp: Optional[float] = None,
    layout_row: Optional[Dict[str, Any]] = None,
    layout_bom: Optional[Dict[str, str]] = None,
    layout_azimuth: float = 180.0,
    boundaries: Optional[Sequence[Sequence[Any]]] = None,
    slope_img_png: Optional[bytes] = None,
    **_kwargs,
) -> bytes:
    """A4 unified report: summary → SiteIQ → TerrainIQ → YieldIQ → PVMath score → disclaimers."""
    scr = screening or {}
    cap = scr.get("capacity") or {}
    if not area_ha:
        try:
            area_ha = float(cap.get("area_ha") or 0)
        except (TypeError, ValueError):
            area_ha = 0.0
    if topo and not area_ha:
        try:
            area_ha = float(topo.get("area_ha") or 0)
        except (TypeError, ValueError):
            pass

    mount_type = resolve_mount_type(mount_type, layout_row)
    if not selected_config_key and layout_row:
        selected_config_key = yield_config_key_from_layout_row(layout_row)

    final_score = _compute_final_score(
        score,
        scr,
        yield_result,
        selected_config_key,
        mount_type=mount_type,
        layout_row=layout_row,
        lat=lat,
        lon=lon,
        country=country,
        capacity_mwp=(selected_dc_kwp / 1000.0) if selected_dc_kwp else None,
        terrain_confirmed=bool(topo),
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.9 * cm,
    )

    footer_date = datetime.now().strftime("%d %b %Y")

    def _make_canvas(*args, **kwargs):
        c = _NumberedCanvas(*args, **kwargs)
        c._footer_date = footer_date
        return c

    story: List = []
    story += _project_summary_flowables(
        project_name=project_name,
        country=country,
        location_label=location_label,
        lat=lat,
        lon=lon,
        land_use=land_use,
        mount_type=mount_type,
        area_ha=area_ha,
        layout_dc_kwp=selected_dc_kwp,
    )

    if lat is not None and lon is not None:
        story += build_siteiq_flowables(
            screening=scr,
            topo=topo,
            score=score,
            country=country,
            land_use=land_use,
            mount_type=mount_type,
            lat=lat,
            lon=lon,
            area_ha=area_ha,
        )

    if lat is not None and lon is not None:
        story += build_terrain_section_flowables(
            topo,
            project_name=project_name,
            country=country,
            location_label=location_label,
            lat=lat,
            lon=lon,
            land_use=land_use,
            mount_type=mount_type,
            boundaries=boundaries,
            slope_img_png=slope_img_png,
        )

    story += build_layoutiq_flowables(
        layout_row,
        bom=layout_bom,
        azimuth=layout_azimuth,
        mount_type=mount_type,
    )

    story += build_yieldiq_flowables(
        yield_result=yield_result,
        mount_type=mount_type,
        selected_config_key=selected_config_key,
        selected_dc_kwp=selected_dc_kwp,
        layout_row=layout_row,
    )

    if final_score:
        story += _pvmath_score_flowables(final_score)
    story += _annex_flowables()

    doc.build(story, canvasmaker=_make_canvas)
    return buf.getvalue()


def _selected_or_best_config(
    yield_result: Optional[Dict[str, Any]],
    selected_config_key: Optional[str],
    *,
    mount_type: str = "Fixed Tilt",
    layout_row: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    if not yield_result:
        return None
    configs = yield_result.get("configs") or {}
    if not configs:
        return None
    mount_filter = "sat" if layout_row_is_tracker(layout_row) or "Tracker" in (mount_type or "") else "fixed"
    if selected_config_key and selected_config_key in configs:
        tracker = "Tracker" in selected_config_key
        if mount_filter == "sat" and tracker:
            return configs[selected_config_key]
        if mount_filter == "fixed" and not tracker:
            return configs[selected_config_key]
    visible = [
        k for k in ("1P Fixed", "2P Fixed", "1P Tracker", "2P Tracker")
        if k in configs and ((mount_filter == "sat") == ("Tracker" in k))
    ]
    if not visible:
        visible = list(configs.keys())
    best, best_sy = None, -1.0
    for key in visible:
        cfg = configs[key]
        try:
            sy = float(cfg.get("spec_y") or 0)
        except (TypeError, ValueError):
            sy = 0.0
        if sy > best_sy:
            best_sy, best = sy, cfg
    return best


def _compute_final_score(
    score: Optional[Dict[str, Any]],
    screening: Dict[str, Any],
    yield_result: Optional[Dict[str, Any]],
    selected_config_key: Optional[str],
    *,
    mount_type: str = "Fixed Tilt",
    layout_row: Optional[Dict[str, Any]] = None,
    lat: float | None = None,
    lon: float | None = None,
    country: str = "",
    capacity_mwp: float | None = None,
    terrain_confirmed: bool = False,
) -> Optional[Dict[str, Any]]:
    """Aggregate PVMath score that also factors energy yield, computed last."""
    comps = dict((score or {}).get("components") or {})
    if not comps:
        sc = screening.get("score_components") or {}
        comps = {
            "solar": sc.get("solar"),
            "terrain": sc.get("terrain"),
            "flood": sc.get("flood"),
            "land": sc.get("land"),
            "regulatory": sc.get("regulatory") or sc.get("grid"),
        }
    needed = ("solar", "terrain", "flood", "land", "regulatory")
    if any(comps.get(k) is None for k in needed):
        if score and score.get("pvmath_score") is not None:
            return score
        return None

    cfg = _selected_or_best_config(
        yield_result, selected_config_key, mount_type=mount_type, layout_row=layout_row
    )
    y_score = (
        yield_subscore(
            cfg.get("spec_y"),
            cfg.get("cf"),
            lat=lat,
            lon=lon,
            country=country,
        )
        if cfg
        else None
    )

    return unified_pvmath_score(
        solar_score=int(comps["solar"]),
        terrain_score=int(comps["terrain"]),
        flood_score=int(comps["flood"]),
        land_score=int(comps["land"]),
        regulatory_score=int(comps["regulatory"]),
        yield_score=y_score,
        terrain_confirmed=terrain_confirmed,
        capacity_mwp=capacity_mwp,
    )
