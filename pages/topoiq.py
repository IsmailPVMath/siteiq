import streamlit as st
import numpy as np
import requests
import math
import io
import concurrent.futures
import csv
import xml.etree.ElementTree as ET
from xml.dom import minidom
import zipfile
import json
from PIL import Image
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from datetime import datetime
from pvmath_auth import (
    show_paywall,
    increment_usage, is_over_limit, remaining, FREE_LIMIT,
)
from pvmath_styles import inject_styles

# ── optional heavy deps — graceful fallback ──────────────────────────────────
try:
    from scipy.interpolate import griddata
    from scipy.ndimage import gaussian_filter
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    import ezdxf
    HAS_EZDXF = True
except ImportError:
    HAS_EZDXF = False

try:
    from shapely.geometry import shape, Polygon as ShapelyPolygon
    from shapely.ops import unary_union
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

# Largest site boundary TopoIQ will process — larger polygons exhaust tile
# downloads and grid memory on Railway's single Streamlit worker.
MAX_SITE_AREA_HA = 10_000
MAX_DEM_TILES = 80           # pick lower zoom if bbox needs more tiles
MAX_GRID_POINTS = 300_000    # coarsen output grid above this point count
DEM_ZOOM_MIN = 11
DEM_ZOOM_MAX = 14
TILE_FETCH_WORKERS = 8
from pvmath_kml import (
    BOUNDARY_COLORS,
    MIN_SITE_PARCEL_HA,
    boundaries_from_features,
    guess_boundary_enabled,
    normalize_ring_lonlat,
    parse_kml_features,
    parse_kmz_features,
    read_kml_bytes,
)
def boundaries_union_area_ha(polygon_list):
    """Total area (ha) — union when shapely available, else sum of parts."""
    polys = [p for p in polygon_list if p and len(p) >= 3]
    if not polys:
        return 0.0
    if len(polys) == 1:
        return boundary_area_ha(polys[0])
    if HAS_SHAPELY:
        try:
            shapes = []
            for coords in polys:
                lats = [c[1] for c in coords]
                mean_lat = sum(lats) / len(lats)
                lat_m = 111320.0
                lon_m = 111320.0 * math.cos(math.radians(mean_lat))
                pts = [(c[0] * lon_m, c[1] * lat_m) for c in coords]
                shapes.append(ShapelyPolygon(pts))
            u = unary_union(shapes)
            return round(u.area / 10_000, 2)
        except Exception:
            pass
    return round(sum(boundary_area_ha(p) for p in polys), 2)


def _polygons_mask(X, Y, polygon_list):
    if not polygon_list:
        return np.ones(X.shape, dtype=bool)
    mask = np.zeros(X.shape, dtype=bool)
    for coords in polygon_list:
        if coords and len(coords) >= 3:
            mask |= _polygon_mask(X, Y, coords)
    return mask


def _render_boundaries_map(boundaries, height=380, interactive=False):
    """Show all boundaries — enabled = colour, disabled = grey outline."""
    if not boundaries:
        return None
    all_lats = [c[1] for b in boundaries for c in b["coords"]]
    all_lons = [c[0] for b in boundaries for c in b["coords"]]
    m = folium.Map(
        location=[float(np.mean(all_lats)), float(np.mean(all_lons))],
        zoom_start=13,
        tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        attr="Google Satellite",
    )
    for i, b in enumerate(boundaries):
        on = b.get("enabled", True)
        color = BOUNDARY_COLORS[i % len(BOUNDARY_COLORS)] if on else "#666666"
        folium.Polygon(
            locations=[(c[1], c[0]) for c in b["coords"]],
            color=color,
            fill=True,
            fill_opacity=0.28 if on else 0.04,
            weight=3 if on else 1,
            dash_array=None if on else "6,4",
            tooltip=f"{b['name']} ({'included' if on else 'excluded'})",
        ).add_to(m)
    return st_folium(
        m, width=None, height=height,
        returned_objects=["all_drawings"] if interactive else [],
    )


def _visible_boundaries(bounds, show_all: bool):
    if show_all:
        return bounds
    return [b for b in bounds if b.get("is_primary", True)]


def _render_boundary_manager():
    """Checkbox list — site parcels only by default; full layer list on demand."""
    all_bounds = st.session_state.get("topo_boundaries", [])
    if not all_bounds:
        return
    show_all = st.session_state.get("topo_show_all_layers", False)
    hidden_n = sum(1 for b in all_bounds if not b.get("is_primary", True))
    bounds = _visible_boundaries(all_bounds, show_all)

    st.markdown(
        '<div class="section-hdr" style="margin-top:0.6rem;">'
        '<i class="fa-solid fa-layer-group" style="color:#1565c0;"></i> '
        'Site Boundaries — select for analysis</div>',
        unsafe_allow_html=True,
    )
    if hidden_n and not show_all:
        st.caption(
            f"Showing **{len(bounds)}** site parcel{'s' if len(bounds) != 1 else ''} "
            f"(≥{MIN_SITE_PARCEL_HA:g} ha · site boundaries & buildable areas). "
            f"**{hidden_n}** other layers hidden."
        )
    else:
        st.caption(
            "Site parcels are pre-selected. Uncheck anything you do not want in the terrain run."
        )

    if hidden_n:
        if not show_all:
            if st.button(
                f"Show all layers ({hidden_n} hidden)",
                use_container_width=True,
                key="topo_show_hidden",
            ):
                st.session_state["topo_show_all_layers"] = True
                st.rerun()
        elif st.button("Site parcels only", use_container_width=True, key="topo_hide_extra"):
            st.session_state["topo_show_all_layers"] = False
            st.rerun()

    qa, qb, qc = st.columns(3)
    if qa.button("✓ Enable all", use_container_width=True, key="topo_en_all"):
        for b in bounds:
            b["enabled"] = True
        st.rerun()
    if qb.button("Site areas only", use_container_width=True, key="topo_en_smart"):
        for b in all_bounds:
            if not show_all and not b.get("is_primary", True):
                continue
            b["enabled"] = guess_boundary_enabled(
                b.get("full_name", b["name"]),
                boundary_area_ha(b["coords"]),
                None, None,
            ) or b.get("is_styled_boundary", False)
        st.rerun()
    if qc.button("Clear all", use_container_width=True, key="topo_clr_all"):
        st.session_state["topo_boundaries"] = []
        st.session_state.pop("topo_upload_key", None)
        st.session_state.pop("topo_show_all_layers", None)
        st.rerun()

    remove_ids = []
    for b in bounds:
        area = boundary_area_ha(b["coords"])
        n_vert = len(b["coords"])
        tag = ""
        if b.get("is_styled_boundary"):
            tag = ' <span style="color:#1565c0;font-size:0.75rem;">● site parcel</span>'
        row_cb, row_txt, row_rm = st.columns([0.06, 0.84, 0.10])
        with row_cb:
            b["enabled"] = st.checkbox(
                "on",
                value=b.get("enabled", True),
                key=f"topo_en_{b['id']}",
                label_visibility="collapsed",
            )
        with row_txt:
            st.markdown(
                f"**{b['name']}**{tag} &nbsp;·&nbsp; {area:,.1f} ha &nbsp;·&nbsp; "
                f"{n_vert} vertices",
                unsafe_allow_html=True,
            )
        with row_rm:
            if st.button("✕", key=f"topo_rm_{b['id']}", help="Remove this boundary"):
                remove_ids.append(b["id"])

    if remove_ids:
        st.session_state["topo_boundaries"] = [
            b for b in all_bounds if b["id"] not in remove_ids
        ]
        st.rerun()

    enabled = [b for b in all_bounds if b.get("enabled")]
    if enabled:
        total = boundaries_union_area_ha([b["coords"] for b in enabled])
        st.success(
            f"**{len(enabled)}** boundar{'y' if len(enabled) == 1 else 'ies'} selected "
            f"· **{total:,.1f} ha** combined"
        )
    else:
        st.warning("No boundaries selected — check at least one to run analysis.")

def boundary_area_ha(polygon_coords):
    """Approximate polygon area (ha). Vertices are (lon, lat) tuples."""
    if not polygon_coords or len(polygon_coords) < 3:
        return 0.0
    lats = [c[1] for c in polygon_coords]
    mean_lat = sum(lats) / len(lats)
    lat_m = 111320.0
    lon_m = 111320.0 * math.cos(math.radians(mean_lat))
    pts = [(c[0] * lon_m, c[1] * lat_m) for c in polygon_coords]
    n = len(pts)
    area_m2 = abs(sum(
        pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
        for i in range(n)
    )) / 2.0
    return round(area_m2 / 10_000, 2)


def _area_limit_message(area_ha: float) -> str:
    return (
        f"Site boundary is {area_ha:,.0f} ha — TopoIQ supports sites up to "
        f"{MAX_SITE_AREA_HA:,} ha. Draw or upload a smaller boundary, or "
        f"split the site into sections."
    )


def generate_pdf_report(
    fname, lat_c, lon_c, area_ha, grid_spacing,
    z_min, z_max, z_range, mean_slope, max_slope,
    pct_over5, pct_over10,
    slope_img_buf,
    verdict_label, verdict_detail,
    project_name="", country="",
    slope_bins=None
):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                         Table, TableStyle, Image as RLImage,
                                         HRFlowable)
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
    except ImportError:
        return None

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=15*mm, bottomMargin=15*mm,
                            leftMargin=18*mm, rightMargin=18*mm)

    W, _ = A4
    usable = W - 36*mm

    styles = getSampleStyleSheet()
    DARK_BLUE = colors.HexColor("#0d2137")
    MID_BLUE  = colors.HexColor("#1565c0")
    GREEN     = colors.HexColor("#1b5e20")
    ORANGE    = colors.HexColor("#f57c00")
    RED_C     = colors.HexColor("#c62828")
    LIGHT_BG  = colors.HexColor("#f0f4f8")

    title_style = ParagraphStyle("title", fontName="Helvetica-Bold",
                                  fontSize=14, textColor=colors.white,
                                  alignment=TA_LEFT, leading=17)
    sub_style   = ParagraphStyle("sub", fontName="Helvetica",
                                  fontSize=8.5, textColor=colors.HexColor("#b0c4de"),
                                  alignment=2)  # TA_RIGHT = 2
    hdr_style   = ParagraphStyle("hdr", fontName="Helvetica-Bold",
                                  fontSize=11, textColor=MID_BLUE,
                                  spaceBefore=6, spaceAfter=3)
    body_style  = ParagraphStyle("body", fontName="Helvetica",
                                  fontSize=9, textColor=colors.HexColor("#333333"),
                                  leading=13)

    story = []

    header_tbl = Table([[
        Paragraph("TOPOIQ — TERRAIN ANALYSIS REPORT", title_style),
        Paragraph(f"PVMath · pvmath.com", sub_style),
    ]], colWidths=["65%","35%"])
    header_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), colors.HexColor("#1565c0")),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 13),
        ("BOTTOMPADDING", (0,0), (-1,-1), 13),
        ("LEFTPADDING",   (0,0), (-1,-1), 14),
        ("RIGHTPADDING",  (0,0), (-1,-1), 14),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 6*mm))

    story.append(Paragraph("Project Summary", hdr_style))
    info_data = []
    if project_name:
        info_data.append(["Project Name", project_name])
    if country:
        info_data.append(["Location", country])
    info_data += [
        ["Coordinates",     f"Lat {lat_c:.5f}°,  Lon {lon_c:.5f}°"],
        ["Site Area",       f"~{area_ha:.1f} ha  ({area_ha*10000:,.0f} m²)"],
        ["Grid Resolution", f"{grid_spacing} m"],
    ]
    info_tbl = Table(info_data, colWidths=[45*mm, usable-45*mm])
    info_tbl.setStyle(TableStyle([
        ("FONTNAME",      (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",      (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE",      (0,0), (-1,-1), 9),
        ("TEXTCOLOR",     (0,0), (0,-1), DARK_BLUE),
        ("TEXTCOLOR",     (1,0), (1,-1), colors.HexColor("#222")),
        ("BACKGROUND",    (0,0), (-1,-1), LIGHT_BG),
        ("ROWBACKGROUNDS",(0,0), (-1,-1), [colors.white, LIGHT_BG]),
        ("GRID",          (0,0), (-1,-1), 0.3, colors.HexColor("#cccccc")),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 7),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 5*mm))

    story.append(Paragraph("Terrain Metrics", hdr_style))
    metrics_data = [
        ["Parameter", "Value", "Notes"],
        ["Min Elevation",       f"{z_min:.1f} m",        "Lowest point in site boundary"],
        ["Max Elevation",       f"{z_max:.1f} m",        "Highest point in site boundary"],
        ["Elevation Range",     f"{z_range:.1f} m",      "Total relief across site"],
        ["Mean Slope",          f"{mean_slope:.2f}%",    "Average terrain gradient"],
        ["Max Slope",           f"{max_slope:.1f}%",     "Steepest point in site"],
        ["Area > 5% slope",     f"{pct_over5:.1f}%",    "Fraction requiring slope analysis"],
        ["Area > 10% slope",    f"{pct_over10:.1f}%",   "Fraction with challenging grade"],
    ]
    m_tbl = Table(metrics_data, colWidths=[55*mm, 30*mm, usable-85*mm])
    m_tbl.setStyle(TableStyle([
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
        ("FONTSIZE",      (0,0), (-1,-1), 9),
        ("BACKGROUND",    (0,0), (-1,0), MID_BLUE),
        ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, LIGHT_BG]),
        ("GRID",          (0,0), (-1,-1), 0.3, colors.HexColor("#cccccc")),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 7),
        ("ALIGN",         (1,1), (1,-1), "CENTER"),
    ]))
    story.append(m_tbl)
    story.append(Spacer(1, 5*mm))

    story.append(Paragraph("Engineering Verdict", hdr_style))
    if "Excellent" in verdict_label:
        vcolor = GREEN
    elif "Good" in verdict_label:
        vcolor = colors.HexColor("#2e7d32")
    elif "Moderate" in verdict_label:
        vcolor = ORANGE
    else:
        vcolor = RED_C

    verdict_data = [[Paragraph(f"<b>{verdict_label}</b>", ParagraphStyle(
        "verd", fontName="Helvetica-Bold", fontSize=11,
        textColor=colors.white, alignment=TA_CENTER))],
        [Paragraph(verdict_detail, ParagraphStyle(
        "verd2", fontName="Helvetica", fontSize=9,
        textColor=colors.white, alignment=TA_CENTER))]]
    v_tbl = Table(verdict_data, colWidths=[usable])
    v_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), vcolor),
        ("TOPPADDING",    (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("ROUNDEDCORNERS", [5]),
    ]))
    story.append(v_tbl)
    story.append(Spacer(1, 5*mm))

    story.append(Paragraph("Slope Map", hdr_style))
    img_w = usable

    if slope_img_buf:
        # Size the image box from its ACTUAL pixel aspect ratio rather than a
        # hardcoded constant (0.62). matplotlib's bbox_inches="tight" trims the
        # saved PNG to its content bounding box, which does not reliably keep
        # the figure's nominal figsize ratio (10x6.2in) — the colorbar/title
        # eat a different proportion of width vs height each render. Forcing
        # a mismatched fixed height stretched/squashed the chart in the PDF
        # (looked "inverted"/garbled) even though it displayed fine on-screen
        # via st.image's own aspect-preserving use_container_width=True.
        slope_img_buf.seek(0)
        img_h = img_w * 0.62
        try:
            _pil_probe = Image.open(slope_img_buf)
            _iw, _ih = _pil_probe.size
            if _iw > 0 and _ih > 0:
                _ratio = _ih / _iw
                if 0.25 <= _ratio <= 1.3:   # sanity clamp against a corrupt/odd image
                    img_h = img_w * _ratio
        except Exception:
            pass
        slope_img_buf.seek(0)
        slope_img = RLImage(slope_img_buf, width=img_w, height=img_h)
        img_tbl = Table([[slope_img]], colWidths=[img_w], hAlign="CENTER")
        img_tbl.setStyle(TableStyle([
            ("LEFTPADDING",  (0,0), (-1,-1), 0),
            ("RIGHTPADDING", (0,0), (-1,-1), 0),
            ("TOPPADDING",   (0,0), (-1,-1), 0),
            ("BOTTOMPADDING",(0,0), (-1,-1), 0),
        ]))
        story.append(img_tbl)
        story.append(Spacer(1, 2*mm))

        _cap_style = ParagraphStyle(
            "mapcap", fontName="Helvetica", fontSize=7,
            textColor=colors.HexColor("#999"), alignment=TA_CENTER, leading=9
        )
        story.append(Paragraph(
            "Slope Map — steepness (%) derived from elevation across the site grid; "
            "green = flat (&lt;3%), red = steep (&gt;10%).", _cap_style
        ))
    story.append(Spacer(1, 5*mm))

    if slope_bins:
        story.append(Paragraph("Slope Distribution", hdr_style))
        _bin_labels = ["0% – 2.5%", "2.5% – 5%", "5% – 7.5%", "7.5% – 10%", "&gt; 10%"]
        # Same green→yellow→orange→red ramp as the Slope Map colormap (0-15% range),
        # sampled at each bin's representative slope so the table reads as an
        # extension of the map's legend rather than a plain blue/white table.
        _bin_colors = [
            (colors.HexColor("#1b5e20"), colors.white),     # 0–2.5%   dark green
            (colors.HexColor("#66bb6a"), colors.white),     # 2.5–5%   light green
            (colors.HexColor("#d4e157"), colors.HexColor("#1a1a1a")),  # 5–7.5%   yellow-green
            (colors.HexColor("#ffa726"), colors.HexColor("#1a1a1a")),  # 7.5–10%  orange
            (colors.HexColor("#c62828"), colors.white),     # >10%     red
        ]
        bins_data = [["Slope Range", "% of Site Area"]]
        for _lbl, _pct in zip(_bin_labels, slope_bins):
            bins_data.append([Paragraph(_lbl, body_style), f"{_pct:.1f}%"])
        bins_tbl = Table(bins_data, colWidths=[usable*0.6, usable*0.4])
        _bins_style = [
            ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTNAME",      (0,1), (-1,-1), "Helvetica-Bold"),
            ("FONTSIZE",      (0,0), (-1,-1), 9),
            ("BACKGROUND",    (0,0), (-1,0), MID_BLUE),
            ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
            ("GRID",          (0,0), (-1,-1), 0.3, colors.HexColor("#cccccc")),
            ("TOPPADDING",    (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ("LEFTPADDING",   (0,0), (-1,-1), 7),
            ("ALIGN",         (1,1), (1,-1), "CENTER"),
        ]
        # Color only column 1 ("% of Site Area") with the slope ramp — column 0
        # ("Slope Range" labels) stays plain/white, matching the header's own
        # styling for that column.
        for _i, (_bg, _fg) in enumerate(_bin_colors, start=1):
            _bins_style.append(("BACKGROUND", (1,_i), (1,_i), _bg))
            _bins_style.append(("TEXTCOLOR",  (1,_i), (1,_i), _fg))
        bins_tbl.setStyle(TableStyle(_bins_style))
        story.append(bins_tbl)
        story.append(Spacer(1, 5*mm))

    story.append(HRFlowable(width="100%", thickness=0.5,
                             color=colors.HexColor("#cccccc")))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "<b>Data Source:</b> Copernicus DEM GLO-30 (ESA/EC 2021) delivered via AWS Terrain Tiles "
        "(Terrarium format, ~30m native resolution, resampled to specified grid). "
        "Accuracy: ±1–3m RMSE typical. Vegetation/building bias possible in forested or built-up areas. "
        "Recommended for preliminary site assessment. Field survey (LiDAR/GNSS) required for detailed design.",
        ParagraphStyle("footer", fontName="Helvetica", fontSize=7.5,
                       textColor=colors.HexColor("#666"), leading=11)
    ))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "Generated by TopoIQ · PVMath (pvmath.com) · contact@pvmath.com",
        ParagraphStyle("footer2", fontName="Helvetica-Oblique", fontSize=7,
                       textColor=colors.HexColor("#999"), alignment=TA_CENTER)
    ))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


def _normalize_for_display(Z):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.cm as cm
    Zm = np.ma.masked_invalid(Z)
    if Zm.count() == 0:
        return np.zeros((100, 100, 3), dtype=np.uint8)
    norm = (Zm - Zm.min()) / max(Zm.max() - Zm.min(), 1e-6)
    rgba = cm.RdYlBu_r(norm.filled(0))
    rgb = (rgba[:, :, :3] * 255).astype(np.uint8)
    mask = Zm.mask if np.ma.is_masked(Zm) else np.zeros_like(Z, dtype=bool)
    if isinstance(mask, np.ndarray):
        rgb[mask] = [30, 30, 30]
    return rgb


inject_styles(accent="#1565c0", accent_light="#d4e8f8")

st.markdown("""
<style>

    .pvmath-header {
        display: flex; align-items: center; gap: 0.75rem;
        padding: 0.5rem 0 1rem 0; border-bottom: 1.5px solid #d4e8f8; margin-bottom: 1.2rem;
    }
    .pvmath-logo-mark {
        width: 40px; height: 40px; border-radius: 10px;
        background: linear-gradient(135deg, #1565c0, #42a5f5);
        display: flex; align-items: center; justify-content: center; flex-shrink: 0;
    }
    .pvmath-app-name { font-size: 1.75rem; font-weight: 800; letter-spacing: -0.02em; color: #0d1a0d; }
    .pvmath-app-sub  { font-size: 0.88rem; color: #4a6a8a; font-weight: 600; }
    .pvmath-tagline  { font-size: 0.97rem; color: #1a2a4a; margin-top: 0.15rem; font-weight: 500; line-height: 1.6; }

    .section-hdr {
        font-size: 0.72rem; font-weight: 800; text-transform: uppercase;
        letter-spacing: 0.14em; color: #1565c0;
        display: flex; align-items: center; gap: 0.5rem;
        margin: 1.6rem 0 0.85rem 0; padding-bottom: 0.5rem;
        border-bottom: 2.5px solid #d4e8f8;
    }

    .accuracy-card {
        background: #f0f7ff; border: 1px solid #c5daf5;
        border-left: 4px solid #1565c0;
        border-radius: 9px; padding: 0.9rem 1.1rem; margin-top: 0.8rem;
        font-size: 0.88rem;
    }
    .accuracy-card h4 { color: #0d47a1; margin-bottom: 0.35rem; font-size: 0.88rem; font-weight: 800; }
    .accuracy-card p  { color: #1a2a3a; margin: 0.12rem 0; line-height: 1.6; font-weight: 500; }

    .topo-feature-card {
        background: #ffffff;
        border: 1.5px solid #dce8f5;
        border-radius: 12px;
        padding: 0.95rem 1rem;
        margin-bottom: 0.75rem;
        box-shadow: 0 1px 4px rgba(21, 101, 192, 0.06);
        display: flex;
        gap: 0.85rem;
        align-items: flex-start;
        min-height: 74px;
    }
    .topo-feature-icon {
        width: 38px; height: 38px;
        border-radius: 10px;
        background: #e8f2fc;
        color: #1565c0;
        display: flex; align-items: center; justify-content: center;
        flex-shrink: 0;
        font-size: 1rem;
    }
    .topo-feature-title {
        font-size: 0.8rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        color: #0d1a0d;
        line-height: 1.3;
    }
    .topo-feature-desc {
        font-size: 0.8rem;
        color: #4a6a8a;
        font-weight: 500;
        margin-top: 0.28rem;
        line-height: 1.5;
    }

    div[data-testid="metric-container"] {
        background: #f4f8ff; border: 1.5px solid #c8dcf5;
        border-radius: 12px; padding: 1.1rem;
        box-shadow: 0 1px 6px rgba(0,0,0,0.05);
    }

    div[data-testid="stButton"] > button {
        font-family: 'Inter', sans-serif !important;
        font-weight: 700 !important; letter-spacing: -0.01em;
        border-radius: 9px !important;
    }
    div[data-testid="stButton"] > button[kind="primary"] {
        background: linear-gradient(135deg, #1565c0, #0d47a1) !important;
        border: none !important; color: #fff !important;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #1976d2, #1565c0) !important;
        box-shadow: 0 0 20px rgba(21,101,192,0.3) !important;
    }

    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        color: #1565c0 !important; border-bottom-color: #1565c0 !important; font-weight: 800 !important;
    }
    div[data-testid="stTabs"] button[role="tab"] { font-weight: 600 !important; color: #2a3a5a !important; }

    div[data-testid="stDownloadButton"] > button {
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important; border-radius: 8px !important;
    }

    div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea {
        font-family: 'Inter', sans-serif !important;
        border-radius: 8px !important;
    }

    div[data-testid="stAlert"] {
        border-radius: 10px !important; font-weight: 500;
    }

    div[data-testid="stExpander"] {
        border: 1px solid #e2ede2 !important; border-radius: 10px !important;
    }

    /* ── Compact "settings bar" sliders (Grid spacing / Minor / Major contour) ── */
    div[data-testid="stVerticalBlock"]:has(div.pvm-topo-settings) div[data-testid="stSlider"] {
        padding-top: 0.1rem !important;
        margin-bottom: 0 !important;
    }
    div[data-testid="stVerticalBlock"]:has(div.pvm-topo-settings) div[data-testid="stSlider"] label p {
        font-size: 0.78rem !important;
        font-weight: 600 !important;
        white-space: nowrap;
    }
    div[data-testid="stVerticalBlock"]:has(div.pvm-topo-settings) div[data-testid="stSlider"] [data-baseweb="slider"] {
        margin-top: 0.15rem !important;
    }
    div[data-testid="stVerticalBlock"]:has(div.pvm-topo-settings) div[data-testid="column"] {
        padding-left: 0.4rem !important; padding-right: 0.4rem !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="pvmath-header">
  <div class="pvmath-logo-mark">
    <i class="fa-solid fa-mountain" style="color:#fff;font-size:1.1rem;"></i>
  </div>
  <div>
    <div style="display:flex;align-items:baseline;gap:0.5rem;">
      <span class="pvmath-app-name">TopoIQ</span>
      <span class="pvmath-app-sub">by PVMath</span>
    </div>
    <div class="pvmath-tagline">Satellite terrain extraction for solar site engineering — DXF terrain files for detailed 3D study in your CAD software</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ─── Tile utilities ───────────────────────────────────────────────────────────

def deg2tile(lat, lon, zoom):
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(math.radians(lat)) +
             1.0 / math.cos(math.radians(lat))) / math.pi) / 2.0 * n)
    return x, y

def tile2deg(x, y, zoom):
    n = 2 ** zoom
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lat, lon

TILE_PX = 256  # terrarium tiles are always 256x256

def fetch_terrarium_tile(x, y, zoom):
    """Fetch one terrarium DEM tile. Bounds are always returned (computed purely from
    tile indices) so a failed/corrupt fetch can still be placed correctly in the mosaic —
    this is what keeps the grid georeferenced even when some tiles 404 or time out."""
    lat_n, lon_w = tile2deg(x, y, zoom)
    lat_s, lon_e = tile2deg(x + 1, y + 1, zoom)
    bounds = {"lat_n": lat_n, "lat_s": lat_s, "lon_w": lon_w, "lon_e": lon_e}
    url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{zoom}/{x}/{y}.png"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return None, bounds
        img = Image.open(io.BytesIO(r.content)).convert("RGB")
        if img.size != (TILE_PX, TILE_PX):
            return None, bounds
        arr = np.array(img, dtype=np.float32)
        elev = arr[:, :, 0] * 256.0 + arr[:, :, 1] + arr[:, :, 2] / 256.0 - 32768.0
        # Reject physically implausible values — corrupt/blank tiles decode to the
        # terrarium zero-point (~-32768m); real land elevation runs roughly
        # -420m (Dead Sea) to +8849m (Everest). Treat anything outside that as nodata.
        elev = np.where((elev < -500) | (elev > 9000), np.nan, elev)
    except Exception:
        return None, bounds
    return elev, bounds


def tile_count_for_bbox(south, north, west, east, zoom):
    x_min, y_min = deg2tile(north, west, zoom)
    x_max, y_max = deg2tile(south, east, zoom)
    return (x_max - x_min + 1) * (y_max - y_min + 1)


def pick_dem_zoom(south, north, west, east, max_tiles=MAX_DEM_TILES):
    """Choose terrarium zoom — highest detail that stays within tile budget."""
    for zoom in range(DEM_ZOOM_MAX, DEM_ZOOM_MIN - 1, -1):
        if tile_count_for_bbox(south, north, west, east, zoom) <= max_tiles:
            return zoom
    return DEM_ZOOM_MIN


def effective_grid_spacing(p_w, p_e, p_s, p_n, grid_m, lat_c,
                           max_points=MAX_GRID_POINTS):
    """Coarsen grid spacing if bbox × spacing would exceed point budget."""
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat_c))
    width_m = max((p_e - p_w) * m_per_deg_lon, grid_m)
    height_m = max((p_n - p_s) * m_per_deg_lat, grid_m)
    n_cols = max(1, int(math.ceil(width_m / grid_m)))
    n_rows = max(1, int(math.ceil(height_m / grid_m)))
    points = n_rows * n_cols
    if points <= max_points:
        return float(grid_m)
    scale = math.sqrt(points / max_points)
    return float(math.ceil(grid_m * scale))


def get_dem_for_bbox(south, north, west, east, zoom=14):
    x_min, y_min = deg2tile(north, west, zoom)
    x_max, y_max = deg2tile(south, east, zoom)
    tile_list = [
        (tx, ty)
        for ty in range(y_min, y_max + 1)
        for tx in range(x_min, x_max + 1)
    ]
    total = len(tile_list)
    prog = st.progress(0, text=f"Downloading terrain tiles (zoom {zoom})…")
    fetched = {}
    any_success = False
    done = 0

    def _fetch_one(tx_ty):
        tx, ty = tx_ty
        return tx_ty, fetch_terrarium_tile(tx, ty, zoom)

    with concurrent.futures.ThreadPoolExecutor(max_workers=TILE_FETCH_WORKERS) as ex:
        futs = [ex.submit(_fetch_one, t) for t in tile_list]
        for fut in concurrent.futures.as_completed(futs):
            (tx, ty), (elev, bounds) = fut.result()
            fetched[(tx, ty)] = (elev, bounds)
            if elev is not None:
                any_success = True
            done += 1
            prog.progress(done / total, text=f"Downloading tile {done}/{total}…")
    prog.empty()
    if not any_success:
        return None, None, None, None, None

    tile_rows, bounds_grid = [], []
    for ty in range(y_min, y_max + 1):
        row_imgs, row_bounds = [], []
        for tx in range(x_min, x_max + 1):
            elev, bounds = fetched[(tx, ty)]
            if elev is None:
                elev = np.full((TILE_PX, TILE_PX), np.nan, dtype=np.float32)
            row_imgs.append(elev)
            row_bounds.append(bounds)
        tile_rows.append(row_imgs)
        bounds_grid.append(row_bounds)

    mosaic = np.concatenate(
        [np.concatenate(row, axis=1) for row in tile_rows], axis=0
    )
    lat_n_all = bounds_grid[0][0]["lat_n"]
    lat_s_all = bounds_grid[-1][0]["lat_s"]
    lon_w_all = bounds_grid[0][0]["lon_w"]
    lon_e_all = bounds_grid[0][-1]["lon_e"]
    return mosaic, lat_n_all, lat_s_all, lon_w_all, lon_e_all


def _polygon_mask(X, Y, polygon_coords):
    if not polygon_coords or len(polygon_coords) < 3:
        return np.ones(X.shape, dtype=bool)
    if HAS_SHAPELY:
        from shapely.vectorized import contains as shp_contains
        return shp_contains(ShapelyPolygon(polygon_coords), X, Y)
    from matplotlib.path import Path
    pts = np.column_stack([X.ravel(), Y.ravel()])
    return Path(polygon_coords).contains_points(pts).reshape(X.shape)


def resample_to_grid(mosaic, lat_n, lat_s, lon_w, lon_e,
                     polygon_coords=None, polygon_list=None, grid_m=5.0):
    h, w = mosaic.shape
    lat_c = (lat_n + lat_s) / 2
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat_c))

    polys = polygon_list if polygon_list else (
        [polygon_coords] if polygon_coords else []
    )

    if polys:
        all_lons = [c[0] for p in polys for c in p]
        all_lats = [c[1] for p in polys for c in p]
        p_w, p_e = min(all_lons), max(all_lons)
        p_s, p_n = min(all_lats), max(all_lats)
    else:
        p_w, p_e, p_s, p_n = lon_w, lon_e, lat_s, lat_n

    grid_m = effective_grid_spacing(p_w, p_e, p_s, p_n, grid_m, lat_c)
    step_lat = grid_m / m_per_deg_lat
    step_lon = grid_m / m_per_deg_lon

    grid_lons = np.arange(p_w, p_e, step_lon)
    grid_lats = np.arange(p_n, p_s, -step_lat)
    if len(grid_lons) < 2:
        grid_lons = np.array([p_w, p_e])
    if len(grid_lats) < 2:
        grid_lats = np.array([p_n, p_s])
    X, Y = np.meshgrid(grid_lons, grid_lats)

    col = (X - lon_w) / (lon_e - lon_w) * (w - 1)
    row = (lat_n - Y) / (lat_n - lat_s) * (h - 1)
    col = np.clip(col, 0, w - 2).astype(int)
    row = np.clip(row, 0, h - 2).astype(int)
    Z = mosaic[row, col].astype(float)

    if polys:
        Z = np.where(_polygons_mask(X, Y, polys), Z, np.nan)

    return X, Y, Z, grid_m


def compute_slope(Z, grid_m):
    if HAS_SCIPY:
        Zf = gaussian_filter(Z.astype(float), sigma=1)
    else:
        Zf = Z.astype(float)
    dz_dy, dz_dx = np.gradient(Zf, grid_m)
    slope_pct = np.sqrt(dz_dx**2 + dz_dy**2) * 100.0
    return slope_pct


# ─── Export functions ─────────────────────────────────────────────────────────

def export_xyz(X, Y, Z):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Longitude", "Latitude", "Elevation_m"])
    for r in range(X.shape[0]):
        for c in range(X.shape[1]):
            if not np.isnan(Z[r, c]):
                writer.writerow([f"{X[r,c]:.8f}", f"{Y[r,c]:.8f}", f"{Z[r,c]:.3f}"])
    return buf.getvalue().encode()


def export_xyz_projected(X, Y, Z, lat_c, lon_c):
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat_c))
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Easting_m", "Northing_m", "Elevation_m"])
    for r in range(X.shape[0]):
        for c in range(X.shape[1]):
            if not np.isnan(Z[r, c]):
                E = (X[r, c] - lon_c) * m_per_deg_lon
                N = (Y[r, c] - lat_c) * m_per_deg_lat
                writer.writerow([f"{E:.3f}", f"{N:.3f}", f"{Z[r,c]:.3f}"])
    return buf.getvalue().encode()


def export_landxml(X, Y, Z, site_name="TopoIQ_Surface"):
    valid_pts = []
    for r in range(X.shape[0]):
        for c in range(X.shape[1]):
            if not np.isnan(Z[r, c]):
                valid_pts.append((X[r, c], Y[r, c], Z[r, c]))

    if len(valid_pts) < 3:
        return None

    rows, cols = X.shape
    faces = []
    pt_idx = {}
    idx = 1
    for r in range(rows):
        for c in range(cols):
            if not np.isnan(Z[r, c]):
                pt_idx[(r, c)] = idx
                idx += 1

    for r in range(rows - 1):
        for c in range(cols - 1):
            if all((r+dr, c+dc) in pt_idx for dr, dc in
                   [(0,0),(0,1),(1,0),(1,1)]):
                a = pt_idx[(r, c)]
                b = pt_idx[(r, c+1)]
                cc = pt_idx[(r+1, c)]
                d = pt_idx[(r+1, c+1)]
                faces.append((a, b, cc))
                faces.append((b, d, cc))

    root = ET.Element("LandXML", {
        "xmlns": "http://www.landxml.org/schema/LandXML-1.2",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": "http://www.landxml.org/schema/LandXML-1.2 http://www.landxml.org/schema/LandXML1.2/LandXML1.2.xsd",
        "version": "1.2",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M:%S"),
        "language": "English",
        "readOnly": "false"
    })
    ET.SubElement(root, "Units").append(
        ET.Element("Metric", {"areaUnit": "squareMeter",
                              "linearUnit": "meter",
                              "volumeUnit": "cubicMeter"})
    )
    proj = ET.SubElement(root, "Project", {"name": site_name})
    surfaces = ET.SubElement(root, "Surfaces")
    surface = ET.SubElement(surfaces, "Surface", {"name": site_name,
                                                   "desc": "TopoIQ satellite DEM"})
    defn = ET.SubElement(surface, "Definition", {"surfType": "TIN"})
    pnts = ET.SubElement(defn, "Pnts")
    faces_el = ET.SubElement(defn, "Faces")

    for (r, c), i in pt_idx.items():
        ET.SubElement(pnts, "P", {"id": str(i)}).text = \
            f"{Y[r,c]:.8f} {X[r,c]:.8f} {Z[r,c]:.3f}"

    for a, b, c in faces:
        ET.SubElement(faces_el, "F").text = f"{a} {b} {c}"

    xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
    return xml_str.encode("utf-8")


def export_dxf(X, Y, Z, lat_c, lon_c, minor_int=0.5, major_int=1.0):
    if not HAS_EZDXF:
        return None

    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat_c))

    Ex = (X - lon_c) * m_per_deg_lon
    Ny = (Y - lat_c) * m_per_deg_lat

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    doc.layers.add("CONTOUR_MINOR", color=3)
    doc.layers.add("CONTOUR_MAJOR", color=1)
    doc.layers.add("BOUNDARY",      color=5)

    z_valid = Z[~np.isnan(Z)]
    if len(z_valid) == 0:
        return None

    z_min = math.floor(z_valid.min() / minor_int) * minor_int
    z_max = math.ceil(z_valid.max()  / minor_int) * minor_int
    levels = np.arange(z_min, z_max + minor_int, minor_int)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    cs = ax.contour(Ex, Ny, Z, levels=levels)
    plt.close(fig)

    for i, level in enumerate(cs.levels):
        is_major = abs(level % major_int) < 1e-6
        layer = "CONTOUR_MAJOR" if is_major else "CONTOUR_MINOR"
        for seg in cs.allsegs[i]:
            if len(seg) >= 2:
                pts = [(float(p[0]), float(p[1]), float(level)) for p in seg]
                msp.add_lwpolyline([(p[0], p[1]) for p in pts],
                                   dxfattribs={"layer": layer,
                                               "elevation": float(level)})

    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")


def _boundaries_from_file_dict(all_polys: dict, source_key: str):
    """Build session-state boundary list from parsed DXF shapes."""
    out = []
    for i, (name, coords) in enumerate(all_polys.items()):
        area = boundary_area_ha(coords)
        out.append({
            "id": f"{source_key}_{i}",
            "name": name,
            "full_name": name,
            "coords": coords,
            "enabled": guess_boundary_enabled(name, area),
            "is_primary": True,
            "is_styled_boundary": False,
        })
    return out


def parse_dxf_polygons(raw_bytes):
    if not HAS_EZDXF:
        return {}
    try:
        doc = ezdxf.read(io.StringIO(raw_bytes.decode("utf-8", errors="ignore")))
    except Exception:
        try:
            doc = ezdxf.read(io.StringIO(raw_bytes.decode("latin-1", errors="ignore")))
        except Exception:
            return {}

    results = {}
    msp = doc.modelspace()
    idx = 0
    for ent in msp:
        pts = None
        if ent.dxftype() == "LWPOLYLINE":
            if ent.is_closed or ent.dxf.flags & 1:
                pts = [(p[0], p[1]) for p in ent.get_points()]
        elif ent.dxftype() == "POLYLINE":
            verts = list(ent.vertices)
            if len(verts) >= 3:
                pts = [(v.dxf.location.x, v.dxf.location.y) for v in verts]

        if pts and len(pts) >= 3:
            layer = ent.dxf.layer if hasattr(ent.dxf, "layer") else "0"
            key = f"Layer {layer} #{idx}"
            results[key] = pts
            idx += 1

    return results


def load_boundary_file(uploaded):
    raw = uploaded.read()
    name = uploaded.name.lower()
    if name.endswith(".kmz"):
        return raw, "kmz"
    elif name.endswith(".kml"):
        return raw, "kml"
    elif name.endswith(".dxf"):
        return raw, "dxf"
    elif name.endswith(".dwg"):
        if HAS_EZDXF:
            try:
                doc = ezdxf.readfile(io.BytesIO(raw))
                return raw, "dwg_ok"
            except Exception:
                pass
        return raw, "dwg_unsupported"
    return raw, "unknown"


# ─── Main UI ─────────────────────────────────────────────────────────────────

# ── Pre-populate from shared pvm_project ──────────────────────────────────
_proj = st.session_state.get("pvm_project", {})
if _proj.get("name") and not st.session_state.get("topo_project_name"):
    st.session_state["topo_project_name"] = _proj["name"]
if _proj.get("country") and not st.session_state.get("topo_country"):
    st.session_state["topo_country"] = _proj["country"]
if _proj.get("lat") and _proj.get("lon") and not st.session_state.get("topo_center"):
    st.session_state["topo_center"] = [_proj["lat"], _proj["lon"]]
    st.session_state["topo_zoom"] = 14

# Full Mode project with drawn polygon — skip re-entry
# project.py stores polygon as [[lat,lon],...]; topoiq internally uses (lon,lat) — convert
_preloaded_polygon = (
    [(c[1], c[0]) for c in _proj["polygon_coords"]]
    if (_proj.get("mode") == "full" and _proj.get("polygon_coords"))
    else None
)

if "topo_boundaries" not in st.session_state:
    st.session_state["topo_boundaries"] = []

def _proj_boundaries_fingerprint(proj):
    bounds = proj.get("polygon_boundaries")
    if bounds:
        return ("multi", len(bounds), tuple(b.get("id", i) for i, b in enumerate(bounds)))
    pc = proj.get("polygon_coords")
    if pc:
        return ("single", len(pc), round(pc[0][0], 5), round(pc[0][1], 5))
    return None

_proj_fp = _proj_boundaries_fingerprint(_proj)
if _proj_fp and st.session_state.get("topo_proj_fp") != _proj_fp:
    st.session_state["topo_proj_fp"] = _proj_fp
    st.session_state.pop("topo_from_proj", None)

if _proj.get("polygon_boundaries"):
    st.session_state.setdefault("topo_boundaries", [])
    if not st.session_state.get("topo_from_proj"):
        st.session_state["topo_boundaries"] = [
            {
                "id": b.get("id", f"proj_{i}"),
                "name": b.get("name", f"Boundary {i + 1}"),
                "coords": [(c[1], c[0]) for c in b["coords"]],
                "enabled": b.get("enabled", True),
            }
            for i, b in enumerate(_proj["polygon_boundaries"])
            if b.get("coords")
        ]
        st.session_state["topo_from_proj"] = True
elif _preloaded_polygon and not st.session_state.get("topo_from_proj"):
    st.session_state["topo_boundaries"] = [{
        "id": "proj_0",
        "name": "Project boundary",
        "coords": _preloaded_polygon,
        "enabled": True,
    }]
    st.session_state["topo_from_proj"] = True

topo_project_name = st.session_state.get("topo_project_name", "")
topo_country      = st.session_state.get("topo_country", "")

with st.expander("✏️ Project details", expanded=not bool(topo_project_name)):
    _pn_col1, _pn_col2 = st.columns(2)
    topo_project_name = _pn_col1.text_input("Project Name", value=topo_project_name,
                                             placeholder="e.g. Bavaria North – Site A")
    topo_country      = _pn_col2.text_input("Country / Region", value=topo_country,
                                             placeholder="e.g. Germany")
    if topo_project_name:
        st.session_state["topo_project_name"] = topo_project_name
    if topo_country:
        st.session_state["topo_country"] = topo_country

left, right = st.columns([1, 1.4])

with left:
    st.markdown('<div class="section-hdr"><i class="fa-solid fa-draw-polygon" style="color:#1565c0;"></i> Site Boundary</div>', unsafe_allow_html=True)

    if st.session_state.get("topo_from_proj") and st.session_state.get("topo_boundaries"):
        st.markdown(
            f'<div style="background:#e8f5ee;border:1.5px solid #b8ddc8;border-radius:10px;'
            f'padding:0.75rem 1rem;margin-bottom:0.6rem;">'
            f'<span style="font-weight:700;color:#145f34;font-size:0.88rem;">'
            f'<i class="fa-solid fa-circle-check"></i> Boundaries loaded from project</span><br>'
            f'<span style="font-size:0.8rem;color:#3a5a3a;">'
            f'Adjust the checklist below, or upload a KMZ here to replace.</span>'
            f'</div>',
            unsafe_allow_html=True
        )
        _tb = st.session_state["topo_boundaries"]
        if len(_tb) == 1 and _tb[0].get("name") == "Project boundary":
            st.info(
                "Only one boundary is saved on this project (older format). "
                "Re-upload your KMZ in **Project Setup** or below to import all buildable parcels."
            )

    if not st.session_state.get("topo_from_proj"):
        input_method = st.radio("Input method", [
            "📁 Upload KML / KMZ / DXF / DWG",
            "✏️ Draw Site Boundary on Map",
        ], horizontal=True, help="Upload is fastest for utility-scale KMZ exports with multiple parcels.")
    else:
        input_method = "📁 Upload KML / KMZ / DXF / DWG"

    _new_draw = None

    if input_method == "✏️ Draw Site Boundary on Map":

            nav_tab1, nav_tab2 = st.tabs(["🔍 Search by Name", "📍 Enter Coordinates"])

            with nav_tab1:
                search_q = st.text_input("Place name", placeholder="e.g. Rajasthan India or Andalusia Spain",
                                         label_visibility="collapsed")
                if search_q and search_q != st.session_state.get("topo_last_search", ""):
                    try:
                        r = requests.get(
                            "https://nominatim.openstreetmap.org/search",
                            params={"q": search_q, "format": "json", "limit": 1},
                            headers={"User-Agent": "TopoIQ/1.0 (pvmath.com; contact@pvmath.com)"},
                            timeout=10
                        )
                        data = r.json()
                        if data:
                            st.session_state["topo_center"] = [float(data[0]["lat"]), float(data[0]["lon"])]
                            st.session_state["topo_zoom"] = 15
                            st.session_state["topo_last_search"] = search_q
                            st.rerun()
                        else:
                            st.warning("Location not found — try a different name.")
                    except Exception:
                        st.warning("Search unavailable — try coordinates instead.")
                    st.session_state["topo_last_search"] = search_q

            with nav_tab2:
                c1, c2 = st.columns(2)
                with c1:
                    lat_in = st.text_input("↕️ Latitude", placeholder="e.g. 26.8467",
                                           key="coord_lat")
                with c2:
                    lon_in = st.text_input("↔️ Longitude", placeholder="e.g. 80.9462",
                                           key="coord_lon")

                coord_key = f"{lat_in}|{lon_in}"
                if lat_in and lon_in and coord_key != st.session_state.get("topo_last_coord", ""):
                    try:
                        lat_f = float(lat_in.strip())
                        lon_f = float(lon_in.strip())
                        if -90 <= lat_f <= 90 and -180 <= lon_f <= 180:
                            st.session_state["topo_center"] = [lat_f, lon_f]
                            st.session_state["topo_zoom"] = 15
                            st.session_state["topo_last_coord"] = coord_key
                            st.rerun()
                        else:
                            st.error("Latitude must be −90 to 90, Longitude −180 to 180.")
                    except ValueError:
                        st.caption("Type valid decimal numbers (e.g. 26.8467, 80.9462)")

                latlon_paste = st.text_input("Or paste as  lat, lon", placeholder="26.8467, 80.9462",
                                             key="coord_paste")
                if latlon_paste and latlon_paste != st.session_state.get("topo_last_paste", ""):
                    try:
                        parts = latlon_paste.replace(";", ",").split(",")
                        lat_f, lon_f = float(parts[0].strip()), float(parts[1].strip())
                        if -90 <= lat_f <= 90 and -180 <= lon_f <= 180:
                            st.session_state["topo_center"] = [lat_f, lon_f]
                            st.session_state["topo_zoom"] = 15
                            st.session_state["topo_last_paste"] = latlon_paste
                            st.rerun()
                        else:
                            st.error("Coordinates out of range.")
                    except Exception:
                        st.caption("Format: latitude, longitude  (decimal degrees)")

            center = st.session_state.get("topo_center", [30.0, 10.0])
            zoom   = st.session_state.get("topo_zoom", 3)

            st.markdown(
                '<div style="background:rgba(255,193,7,0.08);border:1px solid rgba(255,193,7,0.35);'
                'border-radius:8px;padding:0.5rem 0.9rem;font-size:0.82rem;color:#ddd;margin-bottom:0.4rem;">'
                '<i class="fa-solid fa-pen-to-square" style="color:#ffc107;margin-right:0.5rem;"></i>'
                '<strong>How to draw:</strong> &nbsp;'
                '① Click the <strong>polygon tool</strong> (pentagon icon) in the left toolbar. &nbsp;'
                '② Click each corner of your site boundary — all 4 sides show live as you go. &nbsp;'
                '③ Click <strong>[Finish]</strong> in the toolbar when done — all lines including the closing one will appear.'
                '</div>',
                unsafe_allow_html=True
            )

            m = folium.Map(location=center, zoom_start=zoom,
                           tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                           attr="Google Satellite")

            for _bi, _bb in enumerate(st.session_state.get("topo_boundaries", [])):
                _bc = BOUNDARY_COLORS[_bi % len(BOUNDARY_COLORS)] if _bb.get("enabled") else "#666"
                folium.Polygon(
                    locations=[(c[1], c[0]) for c in _bb["coords"]],
                    color=_bc, fill=True, fill_opacity=0.15, weight=2,
                    tooltip=_bb["name"],
                ).add_to(m)

            _style = {"color": "#ffeb3b", "weight": 5, "opacity": 1.0,
                      "fillColor": "#ffeb3b", "fillOpacity": 0.10}
            Draw(
                export=False,
                draw_options={
                    "polyline": False,
                    "polygon": {
                        "allowIntersection": False,
                        "showArea": True,
                        "shapeOptions": _style,
                    },
                    "rectangle": False,
                    "circle": False,
                    "marker": False,
                    "circlemarker": False,
                },
                edit_options={"edit": False, "remove": True}
            ).add_to(m)

            map_data = st_folium(m, width=None, height=430,
                                 returned_objects=["all_drawings"])

            polygon_coords = None
            if map_data and map_data.get("all_drawings"):
                for feat in map_data["all_drawings"]:
                    geom = feat.get("geometry", {})
                    if geom.get("type") == "LineString":
                        pts = [(c[0], c[1]) for c in geom["coordinates"]]
                        if len(pts) >= 3:
                            if pts[0] != pts[-1]:
                                pts.append(pts[0])
                            polygon_coords = pts
                            break
                    elif geom.get("type") == "Polygon":
                        polygon_coords = [(c[0], c[1]) for c in geom["coordinates"][0]]
                        break

            if polygon_coords:
                _new_draw = polygon_coords
                _drawn_area_ha = boundary_area_ha(polygon_coords)
                if _drawn_area_ha > MAX_SITE_AREA_HA:
                    st.error(_area_limit_message(_drawn_area_ha))
                else:
                    st.success(
                        f"✅ Boundary drawn — {len(polygon_coords)-1} vertices · "
                        f"{_drawn_area_ha:,.1f} ha (added to list below)"
                    )
            else:
                st.caption("Draw your site boundary on the map above.")

    else:
        if st.session_state.get("topo_boundaries"):
            with st.expander("📁 Upload KMZ/KML (replaces boundary list)", expanded=False):
                f = st.file_uploader(
                    "Boundary file",
                    type=["kml", "kmz", "dxf", "dwg"],
                    help="All shapes imported — tracker rows auto-excluded where possible.",
                )
        else:
            f = st.file_uploader(
                "Upload boundary file",
                type=["kml", "kmz", "dxf", "dwg"],
                help="KMZ/KML from Google Earth or GIS — all site parcels, buildable areas, "
                     "and boundaries are imported. Tracker rows are auto-detected and usually excluded.",
            )
        if f:
            file_key = f"{f.name}_{f.size}"
            if st.session_state.get("topo_upload_key") != file_key:
                raw, ftype = load_boundary_file(f)

                if ftype == "dwg_unsupported":
                    st.warning(
                        "**DWG file could not be read directly.**\n\n"
                        "In your CAD software: **File → Save As → AutoCAD DXF** (takes ~5 seconds). "
                        "Then re-upload the `.dxf` file here."
                    )
                    new_bounds = []
                elif ftype == "kmz":
                    new_bounds = boundaries_from_features(
                        parse_kmz_features(raw), file_key
                    )
                elif ftype == "kml":
                    new_bounds = boundaries_from_features(
                        parse_kml_features(raw), file_key
                    )
                elif ftype in ("dxf", "dwg_ok"):
                    new_bounds = _boundaries_from_file_dict(
                        parse_dxf_polygons(raw), file_key
                    )
                else:
                    new_bounds = []

                primary = [b for b in new_bounds if b.get("is_primary", True)]
                if not primary and not new_bounds:
                    st.error(
                        "No site boundaries found. Ensure the KMZ contains buildable-area "
                        f"or project-boundary parcels ≥{MIN_SITE_PARCEL_HA:g} ha."
                    )
                elif not primary:
                    st.warning(
                        "No site parcels auto-detected — showing all layers. "
                        "Use **Site areas only** or check parcels manually."
                    )
                    st.session_state["topo_boundaries"] = new_bounds
                    st.session_state["topo_upload_key"] = file_key
                    st.session_state["topo_show_all_layers"] = True
                    st.session_state.pop("topo_from_proj", None)
                    st.rerun()
                else:
                    st.session_state["topo_boundaries"] = new_bounds
                    st.session_state["topo_upload_key"] = file_key
                    st.session_state["topo_show_all_layers"] = False
                    st.session_state.pop("topo_from_proj", None)
                    hidden_n = len(new_bounds) - len(primary)
                    n_en = sum(1 for b in primary if b["enabled"])
                    msg = (
                        f"Loaded **{len(primary)}** site parcel{'s' if len(primary) != 1 else ''}"
                    )
                    if hidden_n:
                        msg += f" · **{hidden_n}** circuit/layout layers hidden"
                    msg += f" · **{n_en}** ready for analysis"
                    st.success(msg)
                    st.rerun()

    if _new_draw:
        _sig = tuple(round(c[0], 5) for c in _new_draw[: min(8, len(_new_draw))])
        if st.session_state.get("topo_last_draw_sig") != _sig:
            st.session_state["topo_last_draw_sig"] = _sig
            _n = sum(1 for b in st.session_state["topo_boundaries"]
                     if str(b.get("id", "")).startswith("draw_")) + 1
            st.session_state["topo_boundaries"].append({
                "id": f"draw_{_n}",
                "name": f"Drawn boundary {_n}",
                "coords": _new_draw,
                "enabled": True,
            })

    if st.session_state.get("topo_boundaries"):
        _render_boundary_manager()
        _render_boundaries_map(st.session_state["topo_boundaries"], height=360)

    _boundaries = st.session_state.get("topo_boundaries", [])
    _enabled_polys = [b["coords"] for b in _boundaries if b.get("enabled")]

    st.markdown(
        '<div class="section-hdr" style="margin-top:1rem;">'
        '<i class="fa-solid fa-sliders" style="color:#1565c0;"></i> Settings</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="pvm-topo-settings"></div>', unsafe_allow_html=True)
    sc1, sc2, sc3 = st.columns(3)
    grid_spacing = sc1.slider("Grid spacing (m)", min_value=3, max_value=10, value=5, step=1,
                               help="Smaller = finer mesh, more detail, slower processing")
    contour_minor = sc2.slider("Minor contour (m)", min_value=0.1, max_value=2.0, value=0.5, step=0.1)
    contour_major = sc3.slider("Major contour (m)", min_value=0.5, max_value=10.0, value=1.0, step=0.5)

    _site_area_ha = boundaries_union_area_ha(_enabled_polys) if _enabled_polys else None
    _area_over_limit = (
        _site_area_ha is not None and _site_area_ha > MAX_SITE_AREA_HA
    )
    if _area_over_limit:
        st.error(_area_limit_message(_site_area_ha))

    _topo_user = st.session_state.get("pvm_user_id", "guest")
    _topo_left = remaining(_topo_user, "topoiq")
    run = False

    if is_over_limit(_topo_user, "topoiq"):
        show_paywall("TopoIQ")
        run = False
    else:
        if _topo_left <= 1:
            st.warning(f"⚠️ {_topo_left} free analysis remaining after this run.")
        run = st.button("⛰ Run Terrain Analysis", type="primary",
                        use_container_width=True,
                        disabled=(not _enabled_polys or _area_over_limit))
        if not _enabled_polys:
            st.caption("Upload a KMZ or check at least one boundary above to enable analysis.")
        elif _area_over_limit:
            st.caption(f"Reduce selected area below {MAX_SITE_AREA_HA:,} ha to run analysis.")

# ─── Results ──────────────────────────────────────────────────────────────────
with right:
    if run and _enabled_polys:
        _run_area_ha = boundaries_union_area_ha(_enabled_polys)
        if _run_area_ha > MAX_SITE_AREA_HA:
            st.error(_area_limit_message(_run_area_ha))
            st.stop()
        lons_p = [c[0] for poly in _enabled_polys for c in poly]
        lats_p = [c[1] for poly in _enabled_polys for c in poly]
        south, north = min(lats_p) - 0.001, max(lats_p) + 0.001
        west,  east  = min(lons_p) - 0.001, max(lons_p) + 0.001
        lat_c = (south + north) / 2
        lon_c = (west  + east)  / 2
        area_ha = _run_area_ha
        dem_zoom = pick_dem_zoom(south, north, west, east)

        with st.spinner("Fetching satellite terrain data…"):
            mosaic, lat_n, lat_s, lon_w, lon_e = get_dem_for_bbox(
                south, north, west, east, zoom=dem_zoom
            )

        if mosaic is None:
            st.error("Could not fetch terrain data. Check your internet connection.")
            st.stop()

        with st.spinner(f"Processing {grid_spacing}m grid…"):
            X, Y, Z, grid_m_used = resample_to_grid(
                mosaic, lat_n, lat_s, lon_w, lon_e,
                polygon_list=_enabled_polys, grid_m=float(grid_spacing)
            )
            slope = compute_slope(Z, grid_m_used)

        if X.shape[0] < 2 or X.shape[1] < 2:
            st.error(
                f"This boundary is too small for a {grid_spacing}m grid — it only fits "
                f"{X.shape[0]}×{X.shape[1]} point(s). Use a smaller grid spacing (lower the "
                f"Grid spacing slider) or draw a larger boundary, then run again."
            )
            st.stop()

        z_valid = Z[~np.isnan(Z)]
        s_valid = slope[~np.isnan(slope) & ~np.isnan(Z)]

        if len(z_valid) == 0 or len(s_valid) == 0:
            st.error(
                "No elevation data inside the site boundary. "
                "Check the boundary location or try again — this run was not counted."
            )
            st.stop()

        increment_usage(st.session_state.get("pvm_user_id", "guest"), "topoiq")

        if grid_m_used > float(grid_spacing):
            st.info(
                f"Grid coarsened to **{grid_m_used:.0f} m** "
                f"({len(z_valid):,} points) to stay within processing limits."
            )
        if dem_zoom < DEM_ZOOM_MAX:
            st.caption(
                f"DEM fetched at zoom **{dem_zoom}** "
                f"({tile_count_for_bbox(south, north, west, east, dem_zoom)} tiles) "
                f"for this site size — resampled to your output grid."
            )

        m1, m2, m3, m4 = st.columns(4)
        metrics = [
            ("fa-arrow-down", "#e53935", "Min Elevation", f"{z_valid.min():.1f} m"),
            ("fa-arrow-up",   "#43a047", "Max Elevation", f"{z_valid.max():.1f} m"),
            ("fa-wave-square","#1565c0", "Elev Range",    f"{z_valid.max()-z_valid.min():.1f} m"),
            ("fa-percent",    "#f57c00", "Max Slope",     f"{s_valid.max():.1f}%"),
        ]
        for col, (icon, color, label, val) in zip([m1,m2,m3,m4], metrics):
            col.markdown(
                f'<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);'
                f'border-radius:9px;padding:0.8rem 1rem;margin-bottom:0.5rem;">'
                f'<div><i class="fa-solid {icon}" style="color:{color};font-size:0.9rem;"></i></div>'
                f'<div style="font-size:0.7rem;color:#888;text-transform:uppercase;letter-spacing:0.06em;">{label}</div>'
                f'<div style="font-size:1.5rem;font-weight:700;">{val}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

        mean_slope = float(s_valid.mean())
        pct_over5  = float((s_valid > 5).sum() / len(s_valid) * 100)
        pct_over10 = float((s_valid > 10).sum() / len(s_valid) * 100)

        if mean_slope <= 3:
            verdict_label  = "Excellent Terrain"
            verdict_detail = f"Mean slope {mean_slope:.1f}%. Ideal for both fixed tilt and single-axis tracker."
            st.success(f"**{verdict_label}** — {verdict_detail}")
        elif mean_slope <= 6:
            verdict_label  = "Good Terrain"
            verdict_detail = f"Mean slope {mean_slope:.1f}%. Suitable for fixed tilt; single-axis tracker feasible with grading."
            st.success(f"**{verdict_label}** — {verdict_detail}")
        elif mean_slope <= 10:
            verdict_label  = "Moderate Terrain"
            verdict_detail = f"Mean slope {mean_slope:.1f}%. Fixed tilt preferred; tracker design needs careful civil study."
            st.warning(f"**{verdict_label}** — {verdict_detail}")
        else:
            verdict_label  = "Challenging Terrain"
            verdict_detail = f"Mean slope {mean_slope:.1f}%. Significant grading required. Detailed civil study essential."
            st.error(f"**{verdict_label}** — {verdict_detail}")

        st.markdown(
            f'<div style="font-size:1rem;font-weight:600;color:#1a1a1a;'
            f'background:#f0f4f8;border-radius:8px;padding:0.55rem 1rem;margin-top:0.3rem;">'
            f'📐 <b>{area_ha:.1f} ha</b> &nbsp;·&nbsp; '
            f'🔢 <b>{len(z_valid):,}</b> grid points at <b>{grid_m_used:.0f} m</b> &nbsp;·&nbsp; '
            f'⚠️ <b>{pct_over5:.0f}%</b> of site &gt;5% slope &nbsp;·&nbsp; '
            f'🔴 <b>{pct_over10:.0f}%</b> &gt;10% slope'
            f'</div>',
            unsafe_allow_html=True
        )

        st.divider()
        st.markdown('<div class="section-hdr"><i class="fa-solid fa-layer-group" style="color:#1565c0;"></i> Slope Map</div>', unsafe_allow_html=True)

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors

        if HAS_SCIPY:
            dy, dx = np.gradient(Z, grid_m_used, grid_m_used)
            slope_pct = np.sqrt(dx**2 + dy**2) * 100
            # grid_lats runs north→south (np.arange(p_n, p_s, -step_lat)), so row 0
            # of slope_pct is already the northernmost row — matplotlib's default
            # imshow origin ("upper") plots row 0 at the top, which is correct as-is.
            # A previous np.flipud() here flipped north/south, making the map
            # upside-down relative to the satellite boundary view above it.
            Sm = np.ma.masked_invalid(slope_pct)
            fig2, ax2 = plt.subplots(figsize=(10, 6.2))
            fig2.patch.set_facecolor("#0e1117")
            ax2.set_facecolor("#0e1117")
            _slope_colors = [
                (0.000, "#1b5e20"),
                (0.167, "#388e3c"),
                (0.200, "#66bb6a"),
                (0.333, "#d4e157"),
                (0.500, "#ffa726"),
                (0.667, "#f44336"),
                (1.000, "#7f0000"),
            ]
            cmap_slope = mcolors.LinearSegmentedColormap.from_list(
                "solar_slope",
                [(pos, col) for pos, col in _slope_colors], N=512
            )
            im2 = ax2.imshow(Sm, cmap=cmap_slope, vmin=0, vmax=15,
                             interpolation="bilinear", aspect="auto")
            cbar2 = fig2.colorbar(im2, ax=ax2, fraction=0.04, pad=0.03)
            cbar2.set_label("Slope (%)", color="white", fontsize=10)
            cbar2.ax.yaxis.set_tick_params(color="white", labelsize=9)
            plt.setp(cbar2.ax.yaxis.get_ticklabels(), color="white")
            ax2.set_title(f"Slope · {grid_m_used:.0f}m grid  (green<3%, red>10%)",
                          color="white", fontsize=11, pad=8)
            ax2.set_xticks([]); ax2.set_yticks([])
            for spine in ax2.spines.values():
                spine.set_edgecolor("#333")
            plt.tight_layout(pad=0.5)
            pdf_slope_buf = io.BytesIO()
            fig2.savefig(pdf_slope_buf, format="png", dpi=150, bbox_inches="tight", facecolor="#0e1117")
            pdf_slope_buf.seek(0); plt.close(fig2)
            st.image(pdf_slope_buf, use_container_width=True)
            st.caption(
                "Slope is derived from elevation — green = flat (<3%), red = steep (>10%). "
                "Steeper zones need more grading or favor fixed tilt over tracker."
            )
        else:
            pdf_slope_buf = None
            st.info("Install scipy for slope map.")

        st.divider()
        st.markdown('<div class="section-hdr"><i class="fa-solid fa-download" style="color:#1565c0;"></i> Download Outputs</div>', unsafe_allow_html=True)
        fname = f"TopoIQ_{lat_c:.3f}_{lon_c:.3f}_{grid_m_used:.0f}m"

        with st.spinner("Generating PDF report…"):
            pdf_slope_buf_for_pdf = pdf_slope_buf if HAS_SCIPY else None
            _n_slope = len(s_valid)
            _slope_bins = (
                float((s_valid <= 2.5).sum() / _n_slope * 100),
                float(((s_valid > 2.5) & (s_valid <= 5)).sum() / _n_slope * 100),
                float(((s_valid > 5) & (s_valid <= 7.5)).sum() / _n_slope * 100),
                float(((s_valid > 7.5) & (s_valid <= 10)).sum() / _n_slope * 100),
                float((s_valid > 10).sum() / _n_slope * 100),
            ) if _n_slope else None
            pdf_bytes = generate_pdf_report(
                fname=fname, lat_c=lat_c, lon_c=lon_c,
                area_ha=area_ha, grid_spacing=grid_m_used,
                z_min=float(z_valid.min()), z_max=float(z_valid.max()),
                z_range=float(z_valid.max()-z_valid.min()),
                mean_slope=mean_slope, max_slope=float(s_valid.max()),
                pct_over5=pct_over5, pct_over10=pct_over10,
                slope_img_buf=pdf_slope_buf_for_pdf,
                verdict_label=verdict_label,
                verdict_detail=verdict_detail,
                slope_bins=_slope_bins,
                project_name=st.session_state.get("topo_project_name", ""),
                country=st.session_state.get("topo_country", ""),
            )
        if pdf_bytes:
            st.download_button(
                "📄 Download Terrain Report (PDF)",
                pdf_bytes,
                file_name=f"{fname}_report.pdf",
                mime="application/pdf",
                use_container_width=True,
                type="primary",
                help="Full terrain report with maps, metrics and engineering verdict"
            )
            st.divider()

        ex1, ex2, ex3, ex4 = st.columns(4)

        with st.spinner("Generating LandXML…"):
            lxml = export_landxml(X, Y, Z, site_name=fname)
        if lxml:
            ex1.download_button("⬇ LandXML", lxml,
                                file_name=f"{fname}.xml",
                                mime="application/xml",
                                use_container_width=True,
                                help="Import directly into CAD software as TIN surface")

        xyz = export_xyz_projected(X, Y, Z, lat_c, lon_c)
        ex2.download_button("⬇ XYZ Points", xyz,
                            file_name=f"{fname}_xyz.csv",
                            mime="text/csv",
                            use_container_width=True,
                            help="Easting / Northing / Elevation CSV")

        if HAS_EZDXF:
            with st.spinner("Generating DXF contours…"):
                dxf_data = export_dxf(X, Y, Z, lat_c, lon_c,
                                      minor_int=contour_minor,
                                      major_int=contour_major)
            if dxf_data:
                ex3.download_button("⬇ DXF Contours", dxf_data,
                                    file_name=f"{fname}_contours.dxf",
                                    mime="application/dxf",
                                    use_container_width=True,
                                    help="Major + minor contour lines for CAD software / AutoCAD")
        else:
            ex3.info("Install ezdxf for DXF export")

        xyz_geo = export_xyz(X, Y, Z)
        ex4.download_button("⬇ XYZ (Geo)", xyz_geo,
                            file_name=f"{fname}_geo.csv",
                            mime="text/csv",
                            use_container_width=True,
                            help="Lon / Lat / Elevation for GIS / PVsyst")

        st.markdown(f"""
        <div class="accuracy-card">
          <h4><i class="fa-solid fa-circle-info" style="margin-right:0.3rem;"></i> Data Source & Accuracy</h4>
          <p><strong>Source:</strong> Copernicus GLO-30 DEM (ESA/EC, 2021) via AWS Terrain Tiles</p>
          <p><strong>Native resolution:</strong> Copernicus GLO-30 via AWS Terrain Tiles (zoom {dem_zoom}, adaptive)</p>
          <p><strong>Output grid:</strong> {grid_m_used:.0f}m resampled</p>
          <p><strong>Vertical accuracy:</strong> ~4m RMSE globally (better in flat terrain, worse in dense vegetation)</p>
          <p><strong>Recommendation:</strong> Suitable for preliminary layout and civil design starting point.
             Verify critical slope areas with LiDAR before final tracker pile design.</p>
          <p style="color:#e53935;margin-top:0.4rem;">
            <i class="fa-solid fa-triangle-exclamation"></i>
            Dense vegetation (forests) and urban areas may cause elevation overestimation.
            Check against site photos before final use.
          </p>
        </div>
        """, unsafe_allow_html=True)

    else:
        st.caption("Draw or upload your site boundary on the left, then click Run Terrain Analysis.")
        wc1, wc2 = st.columns(2)
        _wcards = [
            (wc1, "fa-satellite", "Satellite DEM",
             "Copernicus GLO-30 · ~2.4 m resolution · global coverage"),
            (wc2, "fa-cube", "Civil 3D ready",
             "LandXML TIN surface · import directly, no conversion"),
            (wc1, "fa-layer-group", "DXF contours",
             "Major & minor contour lines · configurable intervals"),
            (wc2, "fa-table-cells", "XYZ point cloud",
             "Easting / Northing / Elevation CSV for any tool"),
            (wc1, "fa-chart-line", "Slope analysis",
             "Mean slope · % area over threshold · tracker suitability"),
            (wc2, "fa-clipboard-check", "Accuracy report",
             "Source · resolution · RMSE · vegetation warnings"),
        ]
        for _col, _icon, _title, _desc in _wcards:
            _col.markdown(
                f'<div class="topo-feature-card">'
                f'<div class="topo-feature-icon"><i class="fa-solid {_icon}"></i></div>'
                f'<div>'
                f'<div class="topo-feature-title">{_title}</div>'
                f'<div class="topo-feature-desc">{_desc}</div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
