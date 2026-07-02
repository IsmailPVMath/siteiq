"""Unified PVMath project reports — SiteIQ + TerrainIQ + YieldIQ + LayoutIQ deliverables."""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pvmath_brand import COMPANY_NAME, PRODUCT_NAME, TAGLINE
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A1, A3, A4, landscape
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
from layoutiq.tracker_styles import TRACKER_UNIT_STYLES
from layoutiq.tracker_units import build_tracker_unit_polys, count_tracker_units_by_size
from pvmath_geocode import pdf_escape
from pvmath_pdf import SITEIQ_DISCLAIMER_BODY
from pvmath_reports.unified_report import build_unified_pvmath_report_pdf
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
    data = [
        [_lp(c, st["lbl"] if i == 0 else st["body"]) for i, c in enumerate(row)]
        for row in rows
    ]
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
    mount_type: str = "Fixed Tilt",
    area_ha: float = 0.0,
    location_label: str = "",
    screening: Optional[Dict[str, Any]] = None,
    topo: Optional[Dict[str, Any]] = None,
    score: Optional[Dict[str, Any]] = None,
    layout_row: Optional[Dict[str, Any]] = None,
    yield_result: Optional[Dict[str, Any]] = None,
    revenueiq_result: Optional[Dict[str, Any]] = None,
    selected_yield_mwh: Optional[float] = None,
    selected_config_key: Optional[str] = None,
    selected_dc_kwp: Optional[float] = None,
    boundaries: Optional[List[List[Any]]] = None,
    slope_img_png: Optional[bytes] = None,
) -> bytes:
    """A4 unified PVMath report — rich SiteIQ, TerrainIQ, and YieldIQ sections."""
    dc_kwp = selected_dc_kwp
    if not dc_kwp and layout_row:
        try:
            dc_kwp = float(layout_row.get("dc_kwp") or 0) or None
        except (TypeError, ValueError):
            dc_kwp = None
    return build_unified_pvmath_report_pdf(
        project_name=project_name,
        country=country,
        lat=lat,
        lon=lon,
        land_use=land_use,
        mount_type=mount_type,
        area_ha=area_ha,
        location_label=location_label,
        screening=screening,
        topo=topo,
        score=score,
        yield_result=yield_result,
        revenueiq_result=revenueiq_result,
        selected_config_key=selected_config_key,
        selected_dc_kwp=dc_kwp,
        layout_row=layout_row,
        layout_bom=(layout_row or {}).get("bom") if isinstance(layout_row, dict) else None,
        boundaries=boundaries,
        slope_img_png=slope_img_png,
    )


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
        merged.setdefault("tracker_unit_polys", []).extend(lay.get("tracker_unit_polys") or [])
    return merged


def _fit_image(png_bytes: bytes, max_w: float, max_h: float) -> RLImage:
    """RLImage scaled to fit a box while preserving aspect ratio."""
    aspect = 13.0 / 10.0
    try:
        from PIL import Image as PILImage  # pillow is a project dependency

        with PILImage.open(io.BytesIO(png_bytes)) as im:
            if im.height:
                aspect = im.width / im.height
    except Exception:
        pass
    w = max_w
    h = w / aspect
    if h > max_h:
        h = max_h
        w = h * aspect
    return RLImage(io.BytesIO(png_bytes), width=w, height=h)


def _logo_mark(size_mm: float = 11.0) -> Drawing:
    """Rounded PVMath badge matching the website mark (dark base, light top band)."""
    s = size_mm * mm
    band = s * 0.30
    r = s * 0.22
    d = Drawing(s, s)
    # Light top band shows by drawing the whole badge light, then dark below it.
    d.add(Rect(0, 0, s, s, rx=r, ry=r, fillColor=colors.HexColor("#1d9e52"), strokeColor=None))
    d.add(Rect(0, 0, s, s - band, rx=r, ry=r, fillColor=colors.HexColor("#145f34"), strokeColor=None))
    pv = String(s / 2, s * 0.30, "PV", textAnchor="middle",
                fontName="Helvetica-Bold", fontSize=size_mm * 1.35,
                fillColor=colors.white)
    d.add(pv)
    return d


def _logo_block(st) -> Table:
    """PVMath logo lockup (rounded mark + wordmark) for the title block."""
    word = [
        _lp(COMPANY_NAME, ParagraphStyle(
            "logoword", parent=st["h2"], fontSize=16, leading=17, textColor=colors.HexColor("#145f34"),
            spaceBefore=0, spaceAfter=1,
        )),
        _lp(TAGLINE, ParagraphStyle(
            "logotag", parent=st["muted"], fontSize=7, leading=9, textColor=colors.HexColor("#5a7a5a"),
        )),
    ]
    tbl = Table([[_logo_mark(11.0), word]], colWidths=[13 * mm, None])
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (1, 0), (1, 0), 7),
    ]))
    return tbl


# BOM lines surfaced on the A3 sheet (concise "nutshell"); full BOM lives in the CSV.
_A3_BOM_KEYS = [
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
]


def _sidebar_panel(rows: List[List], header: str, st, *, col_widths) -> Table:
    """Boxed info panel with a green header band."""
    data = [[_lp(header, st["white"])] + [_lp("", st["white"])] * (len(col_widths) - 1)]
    data += rows
    tbl = Table(data, colWidths=col_widths)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#145f34")),
        ("SPAN", (0, 0), (-1, 0)),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#1d9e52")),
        ("INNERGRID", (0, 1), (-1, -1), 0.25, colors.HexColor("#d4e8d4")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, 0), 4),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
    ]
    tbl.setStyle(TableStyle(style))
    return tbl


def build_layout_sheet_pdf(
    *,
    project_name: str,
    detail: Dict[str, Any],
    bom: Dict[str, str],
    module_wp: int = 550,
    azimuth: float = 180.0,
    country: str = "",
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    land_use: str = "Standard",
    location_label: str = "",
    drawn_by: str = "PVMath LayoutIQ",
    checked_by: str = "—",
    revision: str = "R0",
    excluded_geojson: Optional[Dict[str, Any]] = None,
    constraint_layers: Optional[Dict[str, Any]] = None,
) -> bytes:
    """A1 landscape engineering sheet: large centred top-view layout + title block sidebar.

    The top view shows the array, the buildable parcel, GIS exclusion zones
    (red hatched) and constraint features (rivers, transmission lines, roads…).
    """
    layout = _merged_layout_for_drawing(detail)
    if not layout:
        raise ValueError("No layout geometry for layout sheet")

    chart_bytes = make_layout_drawing(
        layout,
        project_name,
        module_wp,
        azimuth,
        excluded_geojson=excluded_geojson,
        constraint_layers=constraint_layers,
        big=True,
    )
    page_w, page_h = landscape(A1)
    margin = 14 * mm
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A1),
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
    )
    st = _styles()
    # SimpleDocTemplate adds 6pt frame padding on each side; outer table adds
    # 6pt cell padding top/bottom. Reserve that so the sheet fits one page.
    usable_w = page_w - 2 * margin - 12
    usable_h = page_h - 2 * margin - 12
    row_h = usable_h - 12

    sidebar_w = 150 * mm
    gap = 6 * mm
    main_w = usable_w - sidebar_w - gap

    layout_img = _fit_image(chart_bytes, main_w - 14, row_h - 4)

    is_tracker = bool(layout.get("is_tracker"))
    mount_str = "Single-Axis Tracker (SAT)" if is_tracker else f"Fixed Tilt · Az {azimuth:g}°"
    coord_str = f"{lat:.5f}, {lon:.5f}" if lat is not None and lon is not None else "—"
    inner = [3.6 * cm, sidebar_w - 3.6 * cm - 12]

    # ── Project summary panel ────────────────────────────────────────────────
    summary_rows = [
        [_lp("Project", st["lbl"]), _lp(project_name or "—", st["body"])],
        [_lp("Location", st["lbl"]), _lp(location_label or country or "—", st["body"])],
        [_lp("Coordinates", st["lbl"]), _lp(coord_str, st["body"])],
        [_lp("Land use", st["lbl"]), _lp(land_use or "—", st["body"])],
        [_lp("Mounting", st["lbl"]), _lp(mount_str, st["body"])],
    ]
    summary_panel = _sidebar_panel(summary_rows, "PROJECT SUMMARY", st, col_widths=inner)

    # ── Key metrics panel ────────────────────────────────────────────────────
    metric_rows = [
        [_lp("Configuration", st["lbl"]), _lp(str(detail.get("label", "—")), st["body"])],
        [_lp("DC capacity", st["lbl"]), _lp(f"{detail.get('dc_kwp', 0):,.1f} kWp", st["body"])],
        [_lp("Modules", st["lbl"]), _lp(f"{detail.get('total_modules', 0):,}", st["body"])],
        [_lp("Pitch / GCR", st["lbl"]), _lp(f"{detail.get('pitch_m', '—')} m · {detail.get('gcr', '—')}", st["body"])],
        [_lp("Site area", st["lbl"]), _lp(f"{detail.get('area_ha', '—')} ha", st["body"])],
        [_lp("Density", st["lbl"]), _lp(f"{detail.get('mw_per_ha', '—')} MWp/ha", st["body"])],
    ]
    metrics_panel = _sidebar_panel(metric_rows, "KEY METRICS", st, col_widths=inner)

    # ── Tracker unit legend (colored swatches + counts) ──────────────────────
    unit_counts = count_tracker_units_by_size(layout)
    legend_panel = None
    if unit_counts:
        swatch_w = 9 * mm
        label_w = sidebar_w - swatch_w - 22 * mm
        qty_w = sidebar_w - swatch_w - label_w - 12
        legend_data = [[_lp("LEGEND — TRACKER UNITS", st["white"]), _lp("", st["white"]), _lp("", st["white"])]]
        swatch_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#145f34")),
            ("SPAN", (0, 0), (-1, 0)),
            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#1d9e52")),
            ("INNERGRID", (0, 1), (-1, -1), 0.25, colors.HexColor("#d4e8d4")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("ALIGN", (2, 1), (2, -1), "RIGHT"),
        ]
        ridx = 1
        for label, qty in unit_counts.items():
            n = int(str(label).rstrip("Ss") or 0)
            style = TRACKER_UNIT_STYLES.get(n, {})
            legend_data.append([
                _lp("", st["body"]),
                _lp(style.get("label", label), st["body"]),
                _lp(f"{qty:,}", st["body"]),
            ])
            swatch_style.append(
                ("BACKGROUND", (0, ridx), (0, ridx), colors.HexColor(style.get("fill", "#64748b")))
            )
            ridx += 1
        legend_data.append([
            _lp("", st["lbl"]),
            _lp("Total units", st["lbl"]),
            _lp(f"{sum(unit_counts.values()):,}", st["lbl"]),
        ])
        legend_panel = Table(legend_data, colWidths=[swatch_w, label_w, qty_w])
        legend_panel.setStyle(TableStyle(swatch_style))

    # ── BOM nutshell panel (curated key lines; full BOM in CSV) ───────────────
    bom_rows = [[_lp("Item", st["lbl"]), _lp("Quantity", st["lbl"])]]
    for key in _A3_BOM_KEYS:
        if key in bom:
            bom_rows.append([_lp(key, st["body"]), _lp(bom[key], st["body"])])
    bom_panel = _sidebar_panel(bom_rows, "BILL OF MATERIALS", st, col_widths=inner)

    # ── Title block (drawn by / revision / scale) + logo ─────────────────────
    half = (sidebar_w - 12) / 2
    tb_rows = [
        [_lp("Drawn by", st["lbl"]), _lp(drawn_by, st["body"])],
        [_lp("Checked", st["lbl"]), _lp(checked_by, st["body"])],
        [_lp("Revision", st["lbl"]), _lp(revision, st["body"])],
        [_lp("Date", st["lbl"]), _lp(date.today().isoformat(), st["body"])],
        [_lp("Sheet", st["lbl"]), _lp("Layout — A1 top view", st["body"])],
        [_lp("Units", st["lbl"]), _lp("WGS84 UTM (m) · layout DXF georeferenced", st["body"])],
    ]
    titleblock = Table(tb_rows, colWidths=[3.0 * cm, sidebar_w - 3.0 * cm - 12])
    titleblock.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#1d9e52")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d4e8d4")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ]))

    logo_row = Table([[_logo_block(st)]], colWidths=[sidebar_w])
    logo_row.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))

    sidebar_items: list = [summary_panel, Spacer(1, 3 * mm), metrics_panel, Spacer(1, 3 * mm)]
    if legend_panel is not None:
        sidebar_items += [legend_panel, Spacer(1, 3 * mm)]
    sidebar_items += [
        bom_panel,
        Spacer(1, 3 * mm),
        titleblock,
        Spacer(1, 2 * mm),
        logo_row,
    ]

    sidebar = Table([[item] for item in sidebar_items], colWidths=[sidebar_w])
    sidebar.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    frame = Table(
        [[layout_img, sidebar]],
        colWidths=[main_w, sidebar_w + gap],
        rowHeights=[row_h],
    )
    frame.setStyle(TableStyle([
        ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ("VALIGN", (1, 0), (1, 0), "TOP"),
        ("BOX", (0, 0), (-1, -1), 1.0, colors.HexColor("#145f34")),
        ("LINEBEFORE", (1, 0), (1, 0), 0.6, colors.HexColor("#1d9e52")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    doc.build([frame])
    return buf.getvalue()


# Backwards-compatible alias (sheet upgraded A3 → A1).
build_layout_a3_pdf = build_layout_sheet_pdf


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
    mount_type: str = "Fixed Tilt",
    area_ha: float = 0.0,
    boundaries: List[List[List[float]]],
    config_key: str,
    pitch_m: float,
    restriction_polygons: Optional[List[List[List[float]]]] = None,
    restriction_geojson: Optional[Dict[str, Any]] = None,
    constraint_layers: Optional[Dict[str, Any]] = None,
    module_h: float = 2.094,
    module_w: float = 1.038,
    module_wp: int = 550,
    setback_m: float = 5.0,
    azimuth: float = 180.0,
    modules_per_string: int = 28,
    inter_string_gap_m: float = 0.5,
    tracker_string_options: Optional[List[int]] = None,
    max_tracker_length_m: float = 260.0,
    rows_per_block: int = 0,
    block_gap_m: float = 0.0,
    ns_gap_1_m: float = 0.0,
    cols_per_block: int = 0,
    ew_gap_m: float = 0.0,
    road_mode: str = "off",
    road_preset: str = "no_roads",
    allow_partial_strings: bool = False,
    row_alignment: str = "horizontal",
    prune_isolated_blocks: bool = True,
    screening: Optional[Dict[str, Any]] = None,
    topo: Optional[Dict[str, Any]] = None,
    score: Optional[Dict[str, Any]] = None,
    layout_row: Optional[Dict[str, Any]] = None,
    yield_result: Optional[Dict[str, Any]] = None,
    selected_yield_mwh: Optional[float] = None,
    location_label: str = "",
    drawn_by: str = "PVMath LayoutIQ",
    revision: str = "R0",
    terrain_files: Optional[Dict[str, bytes]] = None,
) -> bytes:
    """ZIP: PVMath report PDF, A1 layout+BOM PDF, BOM CSV, layout DXF, and an
    optional ``Terrain Data/`` folder (reference JSON, UTM points CSV,
    georeferenced contour DXF — no slope PDF, LandXML or local DXF)."""
    detail = build_layout_detail(
        boundaries=boundaries,
        restriction_polygons=restriction_polygons,
        restriction_geojson=restriction_geojson,
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
        ns_gap_1_m=ns_gap_1_m,
        cols_per_block=cols_per_block,
        ew_gap_m=ew_gap_m,
        road_mode=road_mode,
        road_preset=road_preset,
        allow_partial_strings=allow_partial_strings,
        row_alignment=row_alignment,
        prune_isolated_blocks=prune_isolated_blocks,
    )
    layouts = detail.get("layouts") or []
    if not layouts:
        raise ValueError("Layout geometry missing for BOM")
    # Build the BOM from the full site (all parcels merged) so string, inverter,
    # post, rail and tracker-unit counts match the on-screen / A1 totals exactly.
    merged = _merged_layout_for_drawing(detail)
    lp = detail.get("layout_params") or {}
    mps = int(lp.get("modules_per_string") or modules_per_string)
    bom = compute_bom(merged, module_wp, detail["n_portrait"], mps, 4, 100.0)

    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in project_name)[:50] or "Project"

    report_pdf = build_pvmath_report_pdf(
        project_name=project_name,
        country=country,
        lat=lat,
        lon=lon,
        land_use=land_use,
        mount_type=mount_type,
        area_ha=area_ha,
        location_label=location_label,
        screening=screening,
        topo=topo,
        score=score,
        yield_result=yield_result,
        selected_yield_mwh=selected_yield_mwh,
        selected_config_key=config_key if layout_row is None else (layout_row.get("config_key") or config_key),
        selected_dc_kwp=float(layout_row["dc_kwp"]) if layout_row and layout_row.get("dc_kwp") else None,
        boundaries=boundaries,
    )
    a1_pdf = build_layout_sheet_pdf(
        project_name=project_name,
        detail=detail,
        bom=bom,
        module_wp=module_wp,
        azimuth=azimuth,
        country=country,
        lat=lat,
        lon=lon,
        land_use=land_use,
        location_label=location_label,
        drawn_by=drawn_by,
        revision=revision,
        excluded_geojson=restriction_geojson,
        constraint_layers=constraint_layers,
    )
    bom_csv = build_bom_csv(bom, project_name)
    dxf_bytes = export_layout_dxf(detail, project_name)

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{safe}_PVMath_Report.pdf", report_pdf)
        zf.writestr(f"{safe}_Layout_A1.pdf", a1_pdf)
        zf.writestr(f"{safe}_BOM.csv", bom_csv)
        zf.writestr(f"{safe}_{config_key}_{pitch_m:g}m_layout.dxf", dxf_bytes)
        for fname, data in (terrain_files or {}).items():
            if data:
                zf.writestr(f"Terrain Data/{fname}", data)
    return zbuf.getvalue()
