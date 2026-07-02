"""A1 electrical layout (page 2) and PVsyst input sheet (page 3)."""

from __future__ import annotations

import io
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from reportlab.graphics import renderPM
from reportlab.graphics.shapes import Drawing, Line, Rect, String as RLString
from reportlab.lib import colors
from reportlab.lib.pagesizes import A1, landscape
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage, PageBreak, Paragraph, Spacer, Table, TableStyle

from layoutiq.sld import build_sld_svg
from pvmath_geocode import pdf_escape


def _lp(text: str, style) -> Paragraph:
    return Paragraph(pdf_escape(str(text)), style)


def _layout_bbox(layout: Dict[str, Any]) -> Tuple[float, float, float, float]:
    xs: List[float] = []
    ys: List[float] = []
    for poly in layout.get("rows_polys") or []:
        if poly is None or getattr(poly, "is_empty", True):
            continue
        bx = poly.bounds
        xs.extend([bx[0], bx[2]])
        ys.extend([bx[1], bx[3]])
    if not xs:
        return 0.0, 0.0, 100.0, 100.0
    return min(xs), min(ys), max(xs), max(ys)


def _world_to_drawing(x: float, y: float, bbox, dw: float, dh: float, margin: float = 8) -> Tuple[float, float]:
    minx, miny, maxx, maxy = bbox
    w = max(maxx - minx, 1.0)
    h = max(maxy - miny, 1.0)
    scale = min((dw - 2 * margin) / w, (dh - 2 * margin) / h)
    ox = margin + (dw - 2 * margin - w * scale) / 2
    oy = margin + (dh - 2 * margin - h * scale) / 2
    return ox + (x - minx) * scale, oy + (y - miny) * scale


def _polys_bounds(polys: List[Any]) -> Optional[Tuple[float, float, float, float]]:
    xs: List[float] = []
    ys: List[float] = []
    for poly in polys:
        if poly is None or getattr(poly, "is_empty", True):
            continue
        bx = poly.bounds
        xs.extend([bx[0], bx[2]])
        ys.extend([bx[1], bx[3]])
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _draw_row_rect(d: Drawing, poly, bbox, width: float, height: float) -> None:
    if poly is None or getattr(poly, "is_empty", True):
        return
    bx = poly.bounds
    x1, y1 = _world_to_drawing(bx[0], bx[1], bbox, width, height)
    x2, y2 = _world_to_drawing(bx[2], bx[3], bbox, width, height)
    d.add(
        Rect(
            min(x1, x2),
            min(y1, y2),
            abs(x2 - x1),
            abs(y2 - y1),
            fillColor=colors.HexColor("#e8ece8"),
            strokeColor=colors.HexColor("#b0b8b0"),
            strokeWidth=0.4,
        )
    )


def build_spatial_electrical_drawing(
    layout: Dict[str, Any],
    electrical: Dict[str, Any],
    width: float = 480,
    height: float = 360,
) -> Drawing:
    """Left-zone indicative electrical layout — rows, inverters, cable routes."""
    d = Drawing(width, height)
    d.add(Rect(0, 0, width, height, fillColor=colors.HexColor("#fafcfa"), strokeColor=colors.HexColor("#d4e8d4"), strokeWidth=0.5))

    bbox = _layout_bbox(layout)
    rows = layout.get("rows_data") or []
    row_polys = layout.get("rows_polys") or []
    n_inv = int((electrical.get("string_sizing") or {}).get("n_inverters") or 1)
    simplify_rows = len(row_polys) > 300

    # PV rows — individual rectangles, or block envelopes on very large sites
    if simplify_rows and rows:
        block_size = max(1, len(rows) // max(n_inv, 1))
        for i in range(n_inv):
            start = i * block_size
            chunk_polys = row_polys[start : start + block_size]
            bounds = _polys_bounds(chunk_polys)
            if not bounds:
                continue
            x1, y1 = _world_to_drawing(bounds[0], bounds[1], bbox, width, height)
            x2, y2 = _world_to_drawing(bounds[2], bounds[3], bbox, width, height)
            d.add(
                Rect(
                    min(x1, x2),
                    min(y1, y2),
                    abs(x2 - x1),
                    abs(y2 - y1),
                    fillColor=colors.HexColor("#e8ece8"),
                    strokeColor=colors.HexColor("#9aa89a"),
                    strokeWidth=0.6,
                )
            )
        d.add(
            RLString(
                12,
                height - 28,
                f"Row blocks ({len(row_polys)} rows simplified)",
                fontSize=6,
                fillColor=colors.HexColor("#666"),
            )
        )
    else:
        for poly in row_polys:
            _draw_row_rect(d, poly, bbox, width, height)

    # Inverter stations at row-block centroids
    block_size = max(1, len(rows) // max(n_inv, 1))
    for i in range(n_inv):
        start = i * block_size
        chunk = rows[start : start + block_size]
        if not chunk:
            continue
        cx = sum(r.get("length_m", 0) for r in chunk) / len(chunk)
        cy = start * 10.0 + 5.0
        px, py = _world_to_drawing(cx, cy + 8, bbox, width, height)
        d.add(Rect(px - 18, py - 8, 36, 16, fillColor=colors.HexColor("#dde3dd"), strokeColor=colors.HexColor("#666"), strokeWidth=0.8))
        d.add(RLString(px, py + 2, f"INV {i + 1}", fontSize=6, fillColor=colors.black, textAnchor="middle"))
        # DC string cable (blue) — representative line to row
        rx, ry = _world_to_drawing(cx, cy, bbox, width, height)
        d.add(Line(rx, ry, px, py, strokeColor=colors.HexColor("#1565c0"), strokeWidth=0.5))

    # MV transformer (bottom centre)
    tx, ty = _world_to_drawing((bbox[0] + bbox[2]) / 2, bbox[1], bbox, width, height)
    d.add(Rect(tx - 12, ty - 20, 24, 24, fillColor=colors.HexColor("#ccc"), strokeColor=colors.HexColor("#333"), strokeWidth=1))
    d.add(RLString(tx, ty - 8, "MV XFMR", fontSize=6, fillColor=colors.black, textAnchor="middle"))

    d.add(RLString(12, height - 14, "N ↑", fontSize=8, fillColor=colors.black))
    d.add(RLString(width / 2, 8, "SCREENING GRADE — NOT FOR CONSTRUCTION", fontSize=7, fillColor=colors.HexColor("#999"), textAnchor="middle"))
    return d


def build_electrical_sidebar_table(electrical: Dict[str, Any], st) -> Table:
    string = electrical.get("string_sizing") or {}
    eb = electrical.get("electrical_bom") or {}
    cables = electrical.get("cables") or {}
    dc_s = cables.get("dc_string_cable") or {}
    dc_m = cables.get("dc_main_cable")
    ac = cables.get("ac_lv_cable") or {}
    comb = cables.get("combiner") or {}

    cfg_rows = [
        ["Module", eb.get("module_model", "—")],
        ["Inverter", eb.get("inverter_model", "—")],
        ["System voltage", f"{eb.get('system_voltage_V', '—')} V DC"],
        ["Modules / string", str(eb.get("modules_per_string", "—"))],
        ["String Voc max", f"{eb.get('Voc_max_string_V', '—')} V"],
        ["String Vmp nom.", f"{eb.get('Vmp_op_string_V', '—')} V"],
        ["Total strings", str(eb.get("total_strings", "—"))],
        ["Inverters", f"{eb.get('inverter_count', '—')}"],
        ["DC:AC ratio", str(eb.get("dc_ac_ratio", "—"))],
    ]
    cfg_tbl = Table(
        [[_lp("STRING CONFIG", st["white"]), _lp("", st["white"])]] + [[_lp(a, st["lbl"]), _lp(b, st["body"])] for a, b in cfg_rows],
        colWidths=[55 * mm, 45 * mm],
    )
    cfg_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#145f34")),
        ("SPAN", (0, 0), (-1, 0)),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#1d9e52")),
        ("INNERGRID", (0, 1), (-1, -1), 0.25, colors.HexColor("#d4e8d4")),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    cable_rows = [
        ["DC String", f"{dc_s.get('size_mm2', '—')} mm²", f"{dc_s.get('total_length_m', '—')} m", f"{dc_s.get('vdrop_pct', '—')}%"],
        ["AC LV", f"{ac.get('size_mm2', '—')} mm²", f"{ac.get('total_length_m', '—')} m", f"{ac.get('vdrop_pct', '—')}%"],
    ]
    if dc_m:
        cable_rows.insert(1, ["DC Main", f"{dc_m.get('size_mm2', '—')} mm²", f"{dc_m.get('total_length_m', '—')} m", f"{dc_m.get('vdrop_pct', '—')}%"])
    if comb.get("combiners_needed"):
        cable_rows.append(["Combiners", "—", f"{comb['combiners_needed']} units", "—"])

    cab_tbl = Table(
        [[_lp("CABLE BOM", st["white"]), _lp("", st["white"]), _lp("", st["white"]), _lp("", st["white"])]]
        + [[_lp(r[0], st["lbl"]), _lp(r[1], st["body"]), _lp(r[2], st["body"]), _lp(r[3], st["body"])] for r in cable_rows],
        colWidths=[22 * mm, 18 * mm, 22 * mm, 14 * mm],
    )
    cab_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#145f34")),
        ("SPAN", (0, 0), (-1, 0)),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#1d9e52")),
        ("INNERGRID", (0, 1), (-1, -1), 0.25, colors.HexColor("#d4e8d4")),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
    ]))
    return Table([[cfg_tbl], [Spacer(1, 3 * mm)], [cab_tbl]], colWidths=[100 * mm])


def build_electrical_page2_flowables(
    *,
    project_name: str,
    layout: Dict[str, Any],
    electrical: Dict[str, Any],
    dc_kwp: float,
    st,
) -> List[Any]:
    """A1 page 2 flowables — spatial drawing + sidebar."""
    spatial = build_spatial_electrical_drawing(layout, electrical, width=480, height=360)
    png_bytes = renderPM.drawToString(spatial, fmt="PNG")
    spatial_img = RLImage(io.BytesIO(png_bytes), width=480, height=360)

    sidebar = build_electrical_sidebar_table(electrical, st)
    svg = build_sld_svg(electrical=electrical, dc_kwp=dc_kwp, total_modules=int(layout.get("total_modules") or 0))
    sld_note = _lp("SLD (indicative) — see sidebar", st["muted"])

    main = Table(
        [[Paragraph(f"<b>{pdf_escape(project_name)}</b> — Electrical Layout — Screening Grade", st["h3"]), ""]],
        colWidths=[400, 100],
    )
    body = Table([[spatial_img, sidebar]], colWidths=[480, 100 * mm])
    body.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    return [
        PageBreak(),
        main,
        Spacer(1, 4 * mm),
        body,
        Spacer(1, 3 * mm),
        sld_note,
        _lp(
            "Electrical layout is indicative — screening grade only. Inverter and cable positions are "
            "approximate. Cable lengths estimated from layout geometry. Not for construction or permitting.",
            st["muted"],
        ),
    ]


def build_pvsyst_page_flowables(
    *,
    project_name: str,
    lat: Optional[float],
    lon: Optional[float],
    elevation_m: Optional[float],
    detail: Dict[str, Any],
    electrical: Dict[str, Any],
    st,
) -> List[Any]:
    string = electrical.get("string_sizing") or {}
    eb = electrical.get("electrical_bom") or {}
    cables = electrical.get("cables") or {}
    dc_s = cables.get("dc_string_cable") or {}
    dc_m = cables.get("dc_main_cable") or {}

    lines = [
        f"PVsyst Input Parameters — {project_name}",
        f"Generated {date.today().isoformat()} by PVMath LayoutIQ",
        "",
        "SITE",
        f"  Latitude: {lat}°N, Longitude: {lon}°E" if lat is not None else "  Coordinates: —",
        f"  Altitude: {elevation_m or '—'} m",
        "  Meteo source: PVGIS ERA5 (download from pvgis.ec.europa.eu for PVsyst import)",
        "",
        "MODULE",
        f"  Model: {eb.get('module_model', '—')}",
        "  Technology: Mono c-Si / Bifacial",
        "",
        "INVERTER",
        f"  Model: {eb.get('inverter_model', '—')}",
        f"  Quantity: {eb.get('inverter_count', '—')}",
        "",
        "ARRAY CONFIGURATION",
        f"  Mount type: {detail.get('mount_type', '—')}",
        f"  Pitch: {detail.get('pitch_m', '—')} m · GCR: {detail.get('gcr', '—')}",
        f"  Modules per string: {eb.get('modules_per_string', '—')}",
        f"  Total strings: {eb.get('total_strings', '—')}",
        f"  DC:AC ratio: {eb.get('dc_ac_ratio', '—')}",
        f"  Total DC: {float(detail.get('dc_kwp') or 0):,.1f} kWp",
        "",
        "ESTIMATED LOSSES (starting point)",
        "  Soiling: 2.5%",
        f"  DC wiring: {dc_s.get('vdrop_pct', '—')}% (string)" + (f" + {dc_m.get('vdrop_pct', '—')}% (main)" if dc_m else ""),
        "  Mismatch: 1.0% · LID: 0.5% · Transformer: 0.8% · Availability: 98%",
        "",
        "Enter values manually in PVsyst Project > Site/Meteo and System tabs.",
    ]
    paras = [PageBreak(), _lp("PVsyst Input Sheet", st["title"])]
    for line in lines:
        paras.append(_lp(line, st["body"] if not line.isupper() or line.endswith(":") else st["h3"]))
        paras.append(Spacer(1, 1 * mm))
    return paras


def build_pvsyst_txt(
    electrical: Dict[str, Any],
    detail: Dict[str, Any],
    *,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    elevation_m: Optional[float] = None,
    project_name: str = "Project",
) -> bytes:
    eb = electrical.get("electrical_bom") or {}
    cables = electrical.get("cables") or {}
    dc_s = cables.get("dc_string_cable") or {}
    dc_m = cables.get("dc_main_cable")
    lines = [
        f"PVsyst Input Parameters — {project_name}",
        f"Generated {date.today().isoformat()} by PVMath LayoutIQ",
        "",
        "SITE",
        f"  Latitude: {lat}°N, Longitude: {lon}°E" if lat is not None and lon is not None else "  Coordinates: —",
        f"  Altitude: {elevation_m or '—'} m",
        "  Meteo: PVGIS ERA5",
        "",
        "ARRAY",
        f"  Mount: {detail.get('mount_type', '—')}",
        f"  Pitch / GCR: {detail.get('pitch_m', '—')} m / {detail.get('gcr', '—')}",
        f"  Module: {eb.get('module_model', '—')}",
        f"  Inverter: {eb.get('inverter_model', '—')} × {eb.get('inverter_count', '—')}",
        f"  Modules/string: {eb.get('modules_per_string', '—')}",
        f"  Total strings: {eb.get('total_strings', '—')}",
        f"  DC:AC: {eb.get('dc_ac_ratio', '—')}",
        f"  Total DC: {detail.get('dc_kwp', '—')} kWp",
        "",
        "LOSSES",
        f"  DC wiring: {dc_s.get('vdrop_pct', '—')}% string"
        + (f" + {dc_m.get('vdrop_pct')}% main" if dc_m else ""),
        "  Soiling 2.5% · Mismatch 1% · LID 0.5% · Transformer 0.8% · Avail 98%",
    ]
    return "\n".join(lines).encode("utf-8")
