"""Unified PVMath project reports — SiteIQ + TerrainIQ + YieldIQ + LayoutIQ deliverables."""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pvmath_brand import PRODUCT_NAME
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from layoutiq.bom import compute_bom
from layoutiq.drawing import make_layout_drawing
from pvmath_geocode import pdf_escape
from pvmath_pdf import SITEIQ_DISCLAIMER_BODY
from pvmath_workflow.layout_detail import build_layout_detail, export_layout_dxf


def _lp(text: str, style) -> Paragraph:
    return Paragraph(pdf_escape(str(text)), style)


def _styles():
    base = getSampleStyleSheet()
    S = lambda name, **kw: ParagraphStyle(name, parent=base["Normal"], **kw)
    green = colors.HexColor("#1d9e52")
    dark = colors.HexColor("#1a2e1a")
    muted = colors.HexColor("#5a7a5a")
    return {
        "title": S("title", fontSize=16, fontName="Helvetica-Bold", textColor=green, spaceAfter=8),
        "h2": S("h2", fontSize=12, fontName="Helvetica-Bold", textColor=dark, spaceBefore=10, spaceAfter=6),
        "h3": S("h3", fontSize=10, fontName="Helvetica-Bold", textColor=dark, spaceAfter=4),
        "body": S("body", fontSize=9, textColor=dark, leading=13),
        "muted": S("muted", fontSize=8, textColor=muted, leading=11),
        "lbl": S("lbl", fontSize=7.5, fontName="Helvetica-Bold", textColor=muted),
        "white": S("white", fontSize=11, fontName="Helvetica-Bold", textColor=colors.white),
    }


def _section_table(rows: List[List[str]], col_widths) -> Table:
    st = _styles()
    data = [[_lp(c, st["lbl"] if i == 0 else st["body"]) for c in row] for row in rows]
    tbl = Table(data, colWidths=col_widths)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f5ee")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#1d9e52")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d4e8d4")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return tbl


def build_pvmath_report_pdf(
    *,
    project_name: str,
    country: str = "",
    lat: float | None = None,
    lon: float | None = None,
    land_use: str = "Standard",
    screening: Optional[Dict[str, Any]] = None,
    topo: Optional[Dict[str, Any]] = None,
    score: Optional[Dict[str, Any]] = None,
    layout_row: Optional[Dict[str, Any]] = None,
    yield_result: Optional[Dict[str, Any]] = None,
    selected_yield_mwh: Optional[float] = None,
) -> bytes:
    """A4 PVMath report: SiteIQ → TerrainIQ → LayoutIQ → YieldIQ → overall score."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
    )
    st = _styles()
    story: list = []

    hdr = Table(
        [[
            _lp("PVMath — Project Intelligence Report", st["white"]),
            _lp("SiteIQ · TerrainIQ · LayoutIQ · YieldIQ", ParagraphStyle(
                "hs", parent=st["muted"], fontSize=8, textColor=colors.HexColor("#d4e8d4"), alignment=TA_RIGHT,
            )),
        ]],
        colWidths=["58%", "42%"],
    )
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1d9e52")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
    ]))
    story += [hdr, Spacer(1, 0.35 * cm)]

    meta_rows = [
        ["Project", project_name or "—"],
        ["Country", country or "—"],
        ["Coordinates", f"{lat:.5f}, {lon:.5f}" if lat is not None and lon is not None else "—"],
        ["Land use", land_use],
        ["Generated", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")],
    ]
    story.append(_section_table([["Field", "Value"]] + meta_rows, [4 * cm, 13 * cm]))
    story.append(Spacer(1, 0.4 * cm))

    # ── SiteIQ ──────────────────────────────────────────────────────────────
    story.append(_lp("1. SiteIQ — Site screening", st["h2"]))
    scr = screening or {}
    solar = scr.get("solar") or {}
    flood = scr.get("flood") or {}
    grid = scr.get("grid") or {}
    reg = scr.get("regulatory") or {}
    nearest = grid.get("nearest") or {}
    grid_detail = grid.get("detail") or "—"
    if grid.get("found") and nearest:
        grid_detail = (
            f"{nearest.get('name', 'Substation')} · {grid.get('distance_km')} km"
            + (f" · {nearest.get('voltage')}" if nearest.get("voltage") else "")
        )
    site_rows = [
        ["Metric", "Rating", "Detail"],
        ["Solar", solar.get("rating", "—"), solar.get("detail", "—")],
        ["Flood", flood.get("risk", "—"), flood.get("detail", "—")],
        ["Grid proximity", grid.get("rating", "—"), grid_detail],
        ["Regulatory", reg.get("status", "—"), reg.get("note", "—")],
    ]
    story.append(_section_table(site_rows, [3.5 * cm, 3 * cm, 10.5 * cm]))
    if scr.get("terrain_note"):
        story.append(Spacer(1, 0.15 * cm))
        story.append(_lp(str(scr["terrain_note"]), st["muted"]))

    # ── TerrainIQ ──────────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(_lp("2. TerrainIQ — Terrain analysis", st["h2"]))
    if topo:
        elev = topo.get("elevation") or {}
        slope = topo.get("slope") or {}
        vf = topo.get("verdict_fixed") or {}
        vt = topo.get("verdict_tracker") or {}
        topo_rows = [
            ["Metric", "Value"],
            ["Elevation range", f"{elev.get('z_min', '—')} – {elev.get('z_max', '—')} m"],
            ["Mean slope", f"{slope.get('mean', '—')}%"],
            ["Max slope", f"{slope.get('max', '—')}%"],
            [">5% area", f"{slope.get('pct_over5', '—')}%"],
            [">10% area", f"{slope.get('pct_over10', '—')}%"],
            ["Terrain source", str(topo.get("terrain_source_used", "—"))],
            ["Fixed Tilt verdict", f"{vf.get('label', '—')} — {vf.get('detail', '')}"],
            ["Tracker verdict", f"{vt.get('label', '—')} — {vt.get('detail', '')}"],
        ]
        story.append(_section_table(topo_rows, [5 * cm, 12 * cm]))
    else:
        story.append(_lp("TerrainIQ not run — draw a site boundary and run terrain analysis.", st["muted"]))

    # ── LayoutIQ ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5 * cm))
    story.append(_lp("3. LayoutIQ — Selected configuration", st["h2"]))
    if layout_row and layout_row.get("success"):
        lr = layout_row
        lay_rows = [
            ["Parameter", "Value"],
            ["Configuration", lr.get("label", "—")],
            ["Pitch", f"{lr.get('pitch_m')} m"],
            ["GCR", f"{lr.get('gcr')}"],
            ["DC capacity", f"{lr.get('dc_kwp', 0):,.1f} kWp"],
            ["Modules", f"{lr.get('total_modules', 0):,}"],
            ["Rows", str(lr.get("total_rows", "—"))],
            ["MW/ha", str(lr.get("mw_per_ha", "—"))],
        ]
        story.append(_section_table(lay_rows, [5 * cm, 12 * cm]))
        story.append(Spacer(1, 0.15 * cm))
        story.append(_lp(
            "Detailed layout drawing, BOM, and DXF are included in the Project Package download.",
            st["muted"],
        ))
    else:
        story.append(_lp("No layout row selected — run LayoutIQ sweep and select a configuration.", st["muted"]))

    # ── YieldIQ ─────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5 * cm))
    story.append(_lp("4. YieldIQ — Energy yield", st["h2"]))
    if yield_result and yield_result.get("configs"):
        if selected_yield_mwh is not None:
            story.append(_lp(
                f"Selected layout estimate: {selected_yield_mwh:,.0f} MWh/yr (preliminary).",
                st["body"],
            ))
            story.append(Spacer(1, 0.2 * cm))
        y_rows = [["Configuration", "Specific yield (kWh/kWp/yr)", "PR %", "GCR"]]
        for _key, cfg in yield_result["configs"].items():
            y_rows.append([
                cfg.get("display_name", _key),
                f"{float(cfg.get('spec_y', 0)):.0f}",
                f"{float(cfg.get('pr', 0)):.1f}" if cfg.get("pr") is not None else "—",
                f"{float(cfg.get('gcr', 0)):.2f}",
            ])
        story.append(_section_table(y_rows, [6 * cm, 5.5 * cm, 2.5 * cm, 3 * cm]))
        if yield_result.get("disclosure"):
            story.append(Spacer(1, 0.15 * cm))
            story.append(_lp(str(yield_result["disclosure"]), st["muted"]))
    else:
        story.append(_lp("YieldIQ not run — select a layout row and run yield analysis.", st["muted"]))

    # ── Overall score ───────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5 * cm))
    story.append(_lp("5. Overall PVMath score", st["h2"]))
    if score and score.get("pvmath_score") is not None:
        story.append(_lp(
            f"Score: {score['pvmath_score']} — {score.get('verdict', '')}",
            ParagraphStyle("sc", parent=st["h3"], fontSize=11, textColor=colors.HexColor("#157a40")),
        ))
        story.append(_lp(score.get("verdict_detail", ""), st["body"]))
    else:
        story.append(_lp(
            "Overall score requires TerrainIQ terrain on a defined site boundary.",
            st["muted"],
        ))

    story += [
        Spacer(1, 0.6 * cm),
        HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#d4e8d4")),
        Spacer(1, 0.25 * cm),
        _lp(SITEIQ_DISCLAIMER_BODY, st["muted"]),
        Spacer(1, 0.2 * cm),
        _lp(
            f"Generated by {PRODUCT_NAME} | For professional use only. "
            "Data: PVGIS (JRC), routed public DEM, OpenStreetMap.",
            st["muted"],
        ),
    ]

    doc.build(story)
    return buf.getvalue()


def _merged_layout_for_drawing(detail: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Merge multi-parcel layout dicts for schematic drawing."""
    layouts = detail.get("layouts") or []
    if not layouts:
        return detail.get("layout")
    if len(layouts) == 1:
        return layouts[0]
    merged = {
        "poly_m": layouts[0]["poly_m"],
        "poly_inset": layouts[0]["poly_inset"],
        "rows_polys": [],
        "rows_data": [],
        "total_modules": detail.get("total_modules", 0),
        "total_rows": detail.get("total_rows", 0),
        "area_ha": detail.get("area_ha", 0),
        "is_tracker": layouts[0].get("is_tracker", False),
    }
    for lay in layouts:
        merged["rows_polys"].extend(lay.get("rows_polys") or [])
        merged["rows_data"].extend(lay.get("rows_data") or [])
    return merged


def build_layout_a3_pdf(
    *,
    project_name: str,
    detail: Dict[str, Any],
    bom: Dict[str, str],
    module_wp: int = 550,
    azimuth: float = 180.0,
) -> bytes:
    """A3 landscape: layout schematic (left) + BOM sidebar (right)."""
    layout = _merged_layout_for_drawing(detail)
    if not layout:
        raise ValueError("No layout geometry for A3 sheet")

    chart_bytes = make_layout_drawing(layout, project_name, module_wp, azimuth)
    page_w, page_h = landscape(A3)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A3),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    st = _styles()

    title_row = Table(
        [[
            _lp(f"LayoutIQ — {project_name}", st["white"]),
            _lp(
                f"{detail.get('label', '')} · {detail.get('pitch_m')} m · GCR {detail.get('gcr')} · "
                f"{detail.get('dc_kwp', 0):,.0f} kWp",
                ParagraphStyle("sub", parent=st["muted"], fontSize=8, textColor=colors.HexColor("#d4e8d4"), alignment=TA_RIGHT),
            ),
        ]],
        colWidths=[page_w * 0.55, page_w * 0.35],
    )
    title_row.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#145f34")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))

    img_w = page_w * 0.68
    img_h = page_h * 0.78
    layout_img = RLImage(io.BytesIO(chart_bytes), width=img_w, height=img_h)

    bom_rows = [[_lp("Bill of materials", st["h3"]), _lp("", st["body"])]]
    bom_rows.append([_lp("Item", st["lbl"]), _lp("Quantity", st["lbl"])])
    for key, val in bom.items():
        bom_rows.append([_lp(key, st["body"]), _lp(val, st["body"])])

    bom_tbl = Table(bom_rows, colWidths=[img_w * 0.38, img_w * 0.22])
    bom_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f5ee")),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#f0faf3")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#1d9e52")),
        ("INNERGRID", (0, 1), (-1, -1), 0.3, colors.HexColor("#d4e8d4")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("SPAN", (0, 0), (1, 0)),
    ]))

    body = Table(
        [[layout_img, bom_tbl]],
        colWidths=[img_w + 6 * mm, page_w - img_w - 30 * mm],
    )
    body.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    story = [
        title_row,
        Spacer(1, 4 * mm),
        body,
        Spacer(1, 3 * mm),
        _lp(
            f"A3 layout sheet · {date.today()} · Preliminary BOM — verify before procurement. "
            "DXF geometry uses local metric coordinates.",
            st["muted"],
        ),
    ]
    doc.build(story)
    return buf.getvalue()


def build_bom_csv(bom: Dict[str, str], project_name: str = "Project") -> bytes:
    """Excel-friendly CSV BOM."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["PVMath LayoutIQ BOM"])
    writer.writerow(["Project", project_name])
    writer.writerow(["Generated", date.today().isoformat()])
    writer.writerow([])
    writer.writerow(["Item", "Value"])
    for key, val in bom.items():
        writer.writerow([key, val])
    return out.getvalue().encode("utf-8-sig")


def build_project_package_zip(
    *,
    project_name: str,
    country: str = "",
    lat: float | None = None,
    lon: float | None = None,
    land_use: str = "Standard",
    boundaries: List[List[List[float]]],
    config_key: str,
    pitch_m: float,
    restriction_polygons: Optional[List[List[List[float]]]] = None,
    module_h: float = 2.094,
    module_w: float = 1.038,
    module_wp: int = 550,
    setback_m: float = 5.0,
    azimuth: float = 180.0,
    modules_per_string: int = 28,
    inter_string_gap_m: float = 0.5,
    tracker_string_options: Optional[List[int]] = None,
    max_tracker_length_m: float = 260.0,
    rows_per_block: int = 2,
    block_gap_m: float = 5.0,
    road_mode: str = "auto",
    road_preset: str = "sat_auto",
    screening: Optional[Dict[str, Any]] = None,
    topo: Optional[Dict[str, Any]] = None,
    score: Optional[Dict[str, Any]] = None,
    layout_row: Optional[Dict[str, Any]] = None,
    yield_result: Optional[Dict[str, Any]] = None,
    selected_yield_mwh: Optional[float] = None,
) -> bytes:
    """ZIP: PVMath report PDF, A3 layout+BOM PDF, BOM CSV, layout DXF."""
    detail = build_layout_detail(
        boundaries=boundaries,
        restriction_polygons=restriction_polygons,
        config_key=config_key,
        pitch_m=pitch_m,
        module_h=module_h,
        module_w=module_w,
        module_wp=module_wp,
        setback_m=setback_m,
        azimuth=azimuth,
        modules_per_string=modules_per_string,
        inter_string_gap_m=inter_string_gap_m,
        tracker_string_options=tracker_string_options,
        max_tracker_length_m=max_tracker_length_m,
        rows_per_block=rows_per_block,
        block_gap_m=block_gap_m,
        road_mode=road_mode,
        road_preset=road_preset,
    )
    layouts = detail.get("layouts") or []
    bom_layout = layouts[0] if layouts else None
    if not bom_layout:
        raise ValueError("Layout geometry missing for BOM")
    merged = _merged_layout_for_drawing(detail)
    lp = detail.get("layout_params") or {}
    mps = int(lp.get("modules_per_string") or modules_per_string)
    bom = compute_bom(bom_layout, module_wp, detail["n_portrait"], mps, 4, 100.0)
    # Scale BOM totals if multi-parcel (module count differs from single-parcel BOM)
    if len(layouts) > 1 and merged:
        ratio = detail["total_modules"] / max(bom_layout["total_modules"], 1)
        if ratio > 1.05:
            bom["DC Capacity"] = f"{detail['dc_kwp']:,.1f} kWp"
            bom["Total Modules"] = f"{detail['total_modules']:,}"
            bom["Total Rows"] = str(detail["total_rows"])
            bom["Site Area"] = f"{detail['area_ha']} ha"
            mw_ha = round(detail["dc_kwp"] / 1000 / detail["area_ha"], 3) if detail["area_ha"] else 0
            bom["Land Use (DC)"] = f"{mw_ha} MWp/ha"

    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in project_name)[:50] or "Project"

    report_pdf = build_pvmath_report_pdf(
        project_name=project_name,
        country=country,
        lat=lat,
        lon=lon,
        land_use=land_use,
        screening=screening,
        topo=topo,
        score=score,
        layout_row=layout_row or {
            "success": True,
            "label": detail.get("label"),
            "pitch_m": detail.get("pitch_m"),
            "gcr": detail.get("gcr"),
            "dc_kwp": detail.get("dc_kwp"),
            "total_modules": detail.get("total_modules"),
            "total_rows": detail.get("total_rows"),
            "mw_per_ha": detail.get("mw_per_ha"),
            "dc_mwp": detail.get("dc_mwp"),
        },
        yield_result=yield_result,
        selected_yield_mwh=selected_yield_mwh,
    )
    a3_pdf = build_layout_a3_pdf(
        project_name=project_name,
        detail=detail,
        bom=bom,
        module_wp=module_wp,
        azimuth=azimuth,
    )
    bom_csv = build_bom_csv(bom, project_name)
    dxf_bytes = export_layout_dxf(detail, project_name)

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{safe}_PVMath_Report.pdf", report_pdf)
        zf.writestr(f"{safe}_Layout_A3.pdf", a3_pdf)
        zf.writestr(f"{safe}_BOM.csv", bom_csv)
        zf.writestr(f"{safe}_{config_key}_{pitch_m:g}m_layout.dxf", dxf_bytes)
    return zbuf.getvalue()
