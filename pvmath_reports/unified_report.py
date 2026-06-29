"""Unified PVMath project intelligence PDF — SiteIQ + TerrainIQ + YieldIQ."""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from pvmath_brand import PRODUCT_NAME
from pvmath_geocode import format_coords, resolve_location_label
from pvmath_pdf import SITEIQ_DISCLAIMER_BODY, append_siteiq_metrics_annexure
from pvmath_reports.common import ACCENT, ACCENT_HDR, BORDER, DARK, MUTED, base_styles, lp, module_banner, module_divider, section_hdr
from pvmath_reports.siteiq_section import build_siteiq_flowables
from pvmath_reports.terrain_section import build_terrain_section_flowables
from pvmath_reports.yieldiq_section import build_yieldiq_flowables
from pvmath_terrain_report import FIXED_THRESHOLDS, TRACKER_THRESHOLDS
from pvmath_workflow.scoring import unified_pvmath_score, yield_subscore


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
        [lp("Generated", st["lbl"]), lp(datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), st["body"])],
    ]
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
            "SiteIQ · TerrainIQ · YieldIQ",
            st,
        ),
        Spacer(1, 0.35 * cm),
        section_hdr("PROJECT SUMMARY", st),
        Spacer(1, 0.15 * cm),
        tbl,
        Spacer(1, 0.4 * cm),
    ]


_SCORE_ROWS = [
    ("Solar resource", "solar"),
    ("Terrain", "terrain"),
    ("Flood risk", "flood"),
    ("Land use", "land"),
    ("Grid / regulatory", "regulatory"),
    ("Energy yield", "yield"),
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
    v_color, v_bg = _verdict_palette(verdict)

    story: List = [
        *module_divider(),
        section_hdr("PVMATH SCORE", st),
        Spacer(1, 0.15 * cm),
        lp(
            "Combines SiteIQ screening, TerrainIQ terrain, and YieldIQ energy yield. "
            "Terrain caps the score on challenging sites. DC capacity is from LayoutIQ.",
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
            f"<b>{verdict or '—'}</b>",
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
    story.append(Spacer(1, 0.3 * cm))

    rows = [[lp("Factor", st["white"]), lp("Score", st["white"])]]
    for label, key in _SCORE_ROWS:
        val = components.get(key)
        if val is None and key == "yield":
            continue
        rows.append([lp(label, st["body"]), lp(f"{int(val)}/100" if val is not None else "—", st["body"])])
    bt = Table(rows, colWidths=[12.5 * cm, 4.5 * cm])
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

    final_score = _compute_final_score(score, scr, yield_result, selected_config_key)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
    )

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

    story += build_yieldiq_flowables(
        yield_result=yield_result,
        mount_type=mount_type,
        selected_config_key=selected_config_key,
        selected_dc_kwp=selected_dc_kwp,
    )

    if final_score:
        story += _pvmath_score_flowables(final_score)
    story += _annex_flowables()

    doc.build(story)
    return buf.getvalue()


def _selected_or_best_config(
    yield_result: Optional[Dict[str, Any]],
    selected_config_key: Optional[str],
) -> Optional[Dict[str, Any]]:
    if not yield_result:
        return None
    configs = yield_result.get("configs") or {}
    if not configs:
        return None
    if selected_config_key and selected_config_key in configs:
        return configs[selected_config_key]
    best, best_sy = None, -1.0
    for cfg in configs.values():
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
        # Not enough to recompute — fall back to the app-provided score as-is.
        if score and score.get("pvmath_score") is not None:
            return score
        return None

    cfg = _selected_or_best_config(yield_result, selected_config_key)
    y_score = yield_subscore(cfg.get("spec_y"), cfg.get("cf")) if cfg else None

    return unified_pvmath_score(
        solar_score=int(comps["solar"]),
        terrain_score=int(comps["terrain"]),
        flood_score=int(comps["flood"]),
        land_score=int(comps["land"]),
        regulatory_score=int(comps["regulatory"]),
        yield_score=y_score,
    )
