"""
pages/layoutiq.py — LayoutIQ: Auto PV Layout + BOM Generator
PVMath Platform · Module 04 — ADMIN PREVIEW (not public)

Algorithm:
  1. Parse polygon (KML / DXF / pasted coords) → local metres
  2. Apply boundary setback (shapely buffer)
  3. Rotate polygon to align rows with specified azimuth
  4. Sweep horizontal band rows at given pitch
  5. Intersect each band with polygon → count modules per row
  6. Rotate rows back → draw on matplotlib schematic
  7. BOM from module count + string/inverter config
"""

import io
import re
import math
import xml.etree.ElementTree as ET
from datetime import date

import streamlit as st
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from shapely.geometry import Polygon, LineString, MultiLineString, box
from shapely.affinity import rotate as shp_rotate

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, HRFlowable, Image as RLImage,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# ─────────────────────────────────────────────────────────────────────────────
# ADMIN GATE
# ─────────────────────────────────────────────────────────────────────────────
ADMIN_EMAIL = "ismailpasha747@gmail.com"
if st.session_state.get("pvm_email", "").lower().strip() != ADMIN_EMAIL:
    st.error("🔒 LayoutIQ is not available yet. Coming soon.")
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap"
      rel="stylesheet">
<style>
html, body, [class*="css"] {
    font-family:'Inter','Segoe UI',system-ui,-apple-system,sans-serif !important;
    font-size:16px !important;
}
[data-testid="stTextInput"] label,
[data-testid="stNumberInput"] label,
[data-testid="stSelectbox"] label,
[data-testid="stFileUploader"] label,
[data-testid="stTextArea"] label,
[data-testid="stSlider"] label {
    font-size:0.97rem !important; font-weight:600 !important; color:#2a1a3a !important;
}
[data-testid="stMetricValue"] { font-size:1.55rem !important; font-weight:700 !important; }
[data-testid="stMetricLabel"] { font-size:0.82rem !important; font-weight:500 !important; }
div[data-testid="stButton"] > button {
    border-radius:8px !important; font-weight:600 !important; font-size:0.97rem !important;
}
.liq-section {
    font-size:1.05rem; font-weight:700; color:#7c3aed;
    border-bottom:2px solid #ede9f0; padding-bottom:0.4rem;
    margin:1.4rem 0 0.9rem 0;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="padding:1.5rem 0 0.5rem 0;border-bottom:2px solid #ede9f0;margin-bottom:1.5rem;">
  <div style="display:flex;align-items:center;gap:0.8rem;margin-bottom:0.4rem;">
    <div style="font-size:0.75rem;font-weight:700;text-transform:uppercase;
                letter-spacing:0.12em;color:#7c3aed;">Module 04</div>
    <div style="font-size:0.65rem;font-weight:700;background:#fef3c7;color:#92400e;
                padding:2px 8px;border-radius:10px;letter-spacing:0.05em;">ADMIN PREVIEW</div>
  </div>
  <h1 style="font-size:2rem;font-weight:800;color:#1a1a2e;margin:0 0 0.3rem 0;">LayoutIQ 📐</h1>
  <p style="color:#5a5a7a;font-size:1rem;margin:0;">
    Auto PV layout from polygon boundary — row sweep algorithm, module count, Bill of Materials
  </p>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# MODULE PRESETS
# ─────────────────────────────────────────────────────────────────────────────
MODULE_PRESETS = {
    "Custom input":                    None,
    "550 Wp — 2094 × 1038 mm (JA)":  {"h": 2.094, "w": 1.038, "wp": 550},
    "580 Wp — 2094 × 1038 mm":        {"h": 2.094, "w": 1.038, "wp": 580},
    "620 Wp — 2172 × 1134 mm":        {"h": 2.172, "w": 1.134, "wp": 620},
    "660 Wp — 2278 × 1134 mm":        {"h": 2.278, "w": 1.134, "wp": 660},
    "700 Wp — 2384 × 1096 mm (LONGi)":{"h": 2.384, "w": 1.096, "wp": 700},
    "720 Wp — 2465 × 1134 mm":        {"h": 2.465, "w": 1.134, "wp": 720},
}

# ─────────────────────────────────────────────────────────────────────────────
# COORDINATE HELPERS
# ─────────────────────────────────────────────────────────────────────────────
_R = 6_371_000.0  # Earth radius (m)

def latlon_to_xy(latlons, ref_lat, ref_lon):
    cos_ref = math.cos(math.radians(ref_lat))
    return [
        ((lon - ref_lon) * math.pi / 180 * _R * cos_ref,
         (lat - ref_lat) * math.pi / 180 * _R)
        for lat, lon in latlons
    ]

def xy_to_latlon(xys, ref_lat, ref_lon):
    cos_ref = math.cos(math.radians(ref_lat))
    return [
        (ref_lat + y * 180 / (math.pi * _R),
         ref_lon + x * 180 / (math.pi * _R * cos_ref))
        for x, y in xys
    ]

# ─────────────────────────────────────────────────────────────────────────────
# POLYGON PARSERS
# ─────────────────────────────────────────────────────────────────────────────

def parse_kml(data: bytes):
    """Extract first polygon (lat, lon) list from KML."""
    try:
        root = ET.fromstring(data.decode("utf-8", errors="ignore"))
        for elem in root.iter():
            if "coordinates" in elem.tag and elem.text:
                pts = []
                for token in elem.text.strip().split():
                    parts = token.split(",")
                    if len(parts) >= 2:
                        try:
                            pts.append((float(parts[1]), float(parts[0])))  # lat, lon
                        except ValueError:
                            pass
                if len(pts) >= 3:
                    return pts
    except Exception:
        pass
    return None

def parse_dxf(data: bytes):
    """Extract first closed LWPOLYLINE from DXF (local coords — no lat/lon)."""
    try:
        import ezdxf
        doc = ezdxf.read(io.StringIO(data.decode("utf-8", errors="ignore")))
        msp = doc.modelspace()
        for e in msp:
            if e.dxftype() == "LWPOLYLINE":
                pts = [(p[1], p[0]) for p in e.get_points()]  # treat X as lon-proxy, Y as lat-proxy
                if len(pts) >= 3:
                    return pts, True  # True = DXF local coords (no lat/lon)
    except Exception:
        pass
    return None, False

def parse_pasted(text: str):
    """Parse pasted 'lat,lon' or 'lat lon' lines."""
    pts = []
    for line in text.strip().splitlines():
        line = re.sub(r"[;|\t]", ",", line).strip()
        m = re.match(r"^(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)$", line)
        if m:
            pts.append((float(m.group(1)), float(m.group(2))))
    return pts if len(pts) >= 3 else None

# ─────────────────────────────────────────────────────────────────────────────
# LAYOUT ALGORITHM
# ─────────────────────────────────────────────────────────────────────────────

def run_layout(latlons, module_h, module_w, n_portrait,
               pitch, setback, azimuth, mounting_type="fixed_tilt", inter_gap=0.01):
    """
    Parameters
    ----------
    latlons       : list of (lat, lon)
    module_h      : module long side (m)
    module_w      : module short side (m)
    n_portrait    : 1 (1P) or 2 (2P)
    pitch         : row-to-row distance (m) — N-S for fixed tilt, E-W for SAT
    setback       : boundary inset (m)
    azimuth       : south-facing azimuth in degrees (fixed tilt only; ignored for SAT)
    mounting_type : "fixed_tilt" or "sat"
    inter_gap     : gap between modules within row (m)

    Fixed Tilt — rows run E-W, pitch measured N-S, azimuth applies.
    SAT        — rows run N-S, pitch measured E-W, azimuth ignored (always N-S axis).
    """
    is_tracker = (mounting_type == "sat")

    lats    = [p[0] for p in latlons]
    lons    = [p[1] for p in latlons]
    ref_lat = sum(lats) / len(lats)
    ref_lon = sum(lons) / len(lons)

    # Local metres
    xy      = latlon_to_xy(latlons, ref_lat, ref_lon)
    poly_m  = Polygon(xy)
    if not poly_m.is_valid:
        poly_m = poly_m.buffer(0)

    area_m2 = poly_m.area

    # Setback
    poly_inset = poly_m.buffer(-setback)
    if poly_inset.is_empty or poly_inset.area < 4:
        return None

    if is_tracker:
        # SAT: rows run N-S. Rotate 90° CCW → N-S axis becomes horizontal in sweep space.
        rot_angle = 90.0
        row_ns    = module_w * n_portrait   # E-W cross-section of one tracker row
        mod_ew    = module_h + inter_gap    # N-S step per module along tracker
    else:
        # Fixed tilt: rows run E-W.
        rot_angle = -(azimuth - 180.0)
        row_ns    = module_h * n_portrait   # N-S footprint of one row
        mod_ew    = module_w + inter_gap    # E-W step per module

    ctr      = poly_inset.centroid
    poly_rot = shp_rotate(poly_inset, rot_angle, origin=(ctr.x, ctr.y))

    minx, miny, maxx, maxy = poly_rot.bounds

    rows_data    = []   # metadata per row
    rows_polys   = []   # shapely polygons for drawing (back-rotated to original)

    y = miny
    while y + row_ns <= maxy:
        band  = box(minx - 1, y, maxx + 1, y + row_ns)
        fp    = poly_rot.intersection(band)

        if not fp.is_empty:
            cy    = y + row_ns / 2
            sweep = LineString([(minx - 1, cy), (maxx + 1, cy)])
            isect = poly_rot.intersection(sweep)

            segs = []
            if isect.geom_type == "LineString":
                segs = [isect]
            elif isect.geom_type == "MultiLineString":
                segs = list(isect.geoms)
            elif isect.geom_type == "GeometryCollection":
                segs = [g for g in isect.geoms
                        if g.geom_type in ("LineString",)]

            for seg in segs:
                n_mod = int(seg.length / mod_ew)
                if n_mod < 1:
                    continue

                actual_len = n_mod * mod_ew
                x0 = seg.bounds[0]

                # Row rectangle in rotated space
                row_rect = box(x0, y, x0 + actual_len, y + row_ns)
                # Rotate back
                row_orig = shp_rotate(row_rect, -rot_angle, origin=(ctr.x, ctr.y))

                rows_polys.append(row_orig)
                rows_data.append({
                    "n_modules":    n_mod,
                    "length_m":     round(actual_len, 2),
                    "y_rot_m":      round(y, 1),
                })

        y += pitch

    if not rows_data:
        return None

    total_modules = sum(r["n_modules"] for r in rows_data)

    return {
        "rows_data":     rows_data,
        "rows_polys":    rows_polys,
        "poly_m":        poly_m,
        "poly_inset":    poly_inset,
        "total_modules": total_modules,
        "total_rows":    len(rows_data),
        "area_m2":       area_m2,
        "area_ha":       round(area_m2 / 10_000, 3),
        "ref_lat":       ref_lat,
        "ref_lon":       ref_lon,
        "row_ns":        row_ns,
        "n_portrait":    n_portrait,
        "is_tracker":    is_tracker,
        "mounting_type": mounting_type,
    }


def compute_bom(layout, module_wp, n_portrait,
                modules_per_string, strings_per_inv, inv_ac_kw):
    total_mod   = layout["total_modules"]
    total_rows  = layout["total_rows"]
    dc_kwp      = total_mod * module_wp / 1000

    total_strings = math.ceil(total_mod / modules_per_string)
    total_inv     = math.ceil(total_strings / strings_per_inv)
    ac_kw         = total_inv * inv_ac_kw
    dc_ac         = round(dc_kwp / ac_kw, 3) if ac_kw else 0

    # Foundations: 1 post every 4 m of row length + 1 at each end (min 2)
    total_posts = sum(
        max(2, math.ceil(r["length_m"] / 4) + 1)
        for r in layout["rows_data"]
    )

    # Purlins / rails: (n_portrait + 1) horizontal rail lines per row
    rails_lines = n_portrait + 1
    total_rail_m = round(sum(r["length_m"] * rails_lines for r in layout["rows_data"]))

    # Clamps: 4 per module (2 mid + 2 end, approximate)
    total_clamps = total_mod * 4

    # DC cable (rough): 10 m per module
    dc_cable_m = total_mod * 10

    # Land use
    mw_per_ha = round(dc_kwp / 1000 / layout["area_ha"], 3) if layout["area_ha"] else 0
    mod_per_ha = round(total_mod / layout["area_ha"], 0) if layout["area_ha"] else 0

    return {
        "DC Capacity":              f"{dc_kwp:,.1f} kWp",
        "AC Capacity (est.)":       f"{ac_kw:,.0f} kW",
        "DC:AC Ratio":              str(dc_ac),
        "Total Modules":            f"{total_mod:,}",
        "Total Rows":               str(total_rows),
        "Modules per String":       str(modules_per_string),
        "Total Strings":            f"{total_strings:,}",
        "Strings per Inverter":     str(strings_per_inv),
        "Total Inverters":          f"{total_inv:,}",
        "Inverter AC (each)":       f"{inv_ac_kw} kW",
        "Site Area":                f"{layout['area_ha']} ha",
        "Land Use (DC)":            f"{mw_per_ha} MWp/ha",
        "Modules / ha":             f"{int(mod_per_ha):,}",
        "Foundation Posts (est.)":  f"{total_posts:,}",
        "Rail / Purlin (m, est.)":  f"{total_rail_m:,} m",
        "Module Clamps (est.)":     f"{total_clamps:,}",
        "DC String Cable (est.)":   f"{dc_cable_m:,} m",
    }


# ─────────────────────────────────────────────────────────────────────────────
# LAYOUT DRAWING
# ─────────────────────────────────────────────────────────────────────────────

def make_layout_drawing(layout: dict, project_name: str,
                        module_wp: int, azimuth: float) -> bytes:
    fig, ax = plt.subplots(figsize=(13, 10))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#e8f4e8")

    # Site polygon
    def _draw_poly(p, fc, ec, alpha, lw, zorder, ls="-"):
        if p.geom_type == "Polygon" and not p.is_empty:
            x, y = p.exterior.xy
            ax.fill(x, y, facecolor=fc, alpha=alpha, zorder=zorder)
            ax.plot(x, y, color=ec, linewidth=lw, linestyle=ls, zorder=zorder + 1)
        elif p.geom_type in ("MultiPolygon", "GeometryCollection"):
            for g in p.geoms:
                if hasattr(g, "exterior"):
                    _draw_poly(g, fc, ec, alpha, lw, zorder, ls)

    _draw_poly(layout["poly_m"],     "#aaaaaa", "#666666", 0.18, 1.2, 1)
    _draw_poly(layout["poly_inset"], "#88aa88", "#888888", 0.10, 0.7, 2, "--")

    # PV rows
    for rp in layout["rows_polys"]:
        _draw_poly(rp, "#2e7d32", "#1b5e20", 0.88, 0.3, 3)

    ax.set_aspect("equal")
    ax.set_xlabel("East →  (metres from centroid)", fontsize=9, labelpad=6)
    ax.set_ylabel("North ↑  (metres from centroid)", fontsize=9, labelpad=6)
    ax.tick_params(labelsize=8)
    ax.grid(True, alpha=0.25, linewidth=0.5)
    ax.spines[["top","right"]].set_visible(False)

    # North arrow
    xl, xr = ax.get_xlim()
    yb, yt = ax.get_ylim()
    dx, dy = xr - xl, yt - yb
    na_x = xr - dx * 0.05
    na_y = yt - dy * 0.04
    ax.annotate("", xy=(na_x, na_y), xytext=(na_x, na_y - dy * 0.08),
                arrowprops=dict(arrowstyle="->", color="#1a2e1a", lw=2))
    ax.text(na_x, na_y + dy * 0.01, "N", ha="center", va="bottom",
            fontsize=11, fontweight="bold", color="#1a2e1a")

    # Scale bar
    raw_len = dx * 0.15
    mag     = 10 ** math.floor(math.log10(raw_len))
    scale_m = round(raw_len / mag) * mag or mag
    sx = xl + dx * 0.04
    sy = yb + dy * 0.03
    ax.plot([sx, sx + scale_m], [sy, sy], "k-", lw=2.5)
    ax.text(sx + scale_m / 2, sy + dy * 0.012, f"{int(scale_m)} m",
            ha="center", va="bottom", fontsize=8)

    dc_kwp  = layout["total_modules"] * module_wp / 1000
    mount_str = "Single-Axis Tracker (SAT)" if layout.get("is_tracker") else f"Fixed Tilt · Az {azimuth}°"
    summary = (f"{layout['total_modules']:,} modules  |  "
               f"{layout['total_rows']} rows  |  "
               f"{dc_kwp:,.0f} kWp  |  {layout['area_ha']} ha  |  "
               f"{mount_str}")
    ax.set_title(f"LayoutIQ — {project_name}\n{summary}",
                 fontsize=10, fontweight="bold", pad=10, color="#1a1a2e")

    ax.legend(handles=[
        mpatches.Patch(color="#2e7d32", alpha=0.88, label="PV rows"),
        mpatches.Patch(color="#aaaaaa", alpha=0.18, label="Site boundary"),
        mpatches.Patch(color="#88aa88", alpha=0.10, label="Setback inset", linestyle="--"),
    ], fontsize=8.5, loc="lower right", framealpha=0.85)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# PDF
# ─────────────────────────────────────────────────────────────────────────────

def build_pdf(project_name, layout, bom, chart_bytes, module_label,
              module_wp, n_portrait, pitch, setback, azimuth) -> bytes:
    buf  = io.BytesIO()
    doc  = SimpleDocTemplate(buf, pagesize=A4,
                              leftMargin=2*cm, rightMargin=2*cm,
                              topMargin=2*cm,  bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    S   = lambda name, **kw: ParagraphStyle(name, parent=styles["Normal"], **kw)
    lbl = S("lbl", fontSize=7.5, fontName="Helvetica-Bold",
            textColor=colors.HexColor("#7c3aed"))
    bod = S("bod", fontSize=9,   textColor=colors.HexColor("#2a2a3a"), leading=13)
    sh  = S("sh",  fontSize=11,  fontName="Helvetica-Bold",
            textColor=colors.HexColor("#4c1d95"), spaceAfter=5)
    nte = S("nte", fontSize=7.5, textColor=colors.HexColor("#8a8a9a"), leading=11)
    def lp(txt, style=bod): return Paragraph(str(txt), style)

    story = []

    # Header
    hdr = Table([[
        lp("LayoutIQ 📐", S("ht", fontSize=15, fontName="Helvetica-Bold",
                             textColor=colors.white)),
        lp("PVMath · Solar Site Intelligence · pvmath.com",
           S("hs", fontSize=8.5, textColor=colors.HexColor("#ddd6fe"),
             alignment=TA_RIGHT)),
    ]], colWidths=["55%","45%"])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), colors.HexColor("#4c1d95")),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0),(-1,-1), 10),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
        ("LEFTPADDING",   (0,0),(-1,-1), 12),
        ("RIGHTPADDING",  (0,0),(-1,-1), 12),
    ]))
    story += [hdr, Spacer(1, 0.35*cm)]

    # Project info
    info = Table([
        [lp("PROJECT",    lbl), lp(project_name, bod),
         lp("DATE",       lbl), lp(str(date.today()), bod)],
        [lp("MODULE",     lbl), lp(module_label, bod),
         lp("MODULE Wp",  lbl), lp(f"{module_wp} Wp", bod)],
        [lp("CONFIG",     lbl), lp(f"{'1P' if n_portrait==1 else '2P'} Portrait — " +
                              ("SAT N-S axis" if mounting_type=='sat' else f"Fixed Tilt · Azimuth {azimuth}°"), bod),
         lp("PITCH / SETBACK", lbl), lp(f"{pitch} m pitch · {setback} m setback", bod)],
    ], colWidths=["2.5cm","6.5cm","3cm","6cm"])
    info.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), colors.HexColor("#f5f3ff")),
        ("BOX",           (0,0),(-1,-1), 0.5, colors.HexColor("#c4b5fd")),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
    ]))
    story += [info, Spacer(1, 0.4*cm)]

    # Layout drawing
    story.append(lp("Layout Schematic", sh))
    story.append(RLImage(io.BytesIO(chart_bytes), width=16*cm, height=12*cm))
    story += [Spacer(1, 0.4*cm)]

    # BOM table
    story.append(lp("Bill of Materials", sh))
    bom_rows = [[lp("Item", lbl), lp("Value", lbl)]]
    for k, v in bom.items():
        bom_rows.append([lp(k, bod), lp(v, bod)])
    bom_tbl = Table(bom_rows, colWidths=["9cm","9cm"])
    bom_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1, 0), colors.HexColor("#ede9f6")),
        ("BOX",           (0,0),(-1,-1), 0.5, colors.HexColor("#c4b5fd")),
        ("INNERGRID",     (0,0),(-1,-1), 0.3, colors.HexColor("#e9d5ff")),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 7),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, colors.HexColor("#faf5ff")]),
    ]))
    story += [bom_tbl, Spacer(1, 0.4*cm),
              HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#c4b5fd")),
              Spacer(1, 0.25*cm)]

    story.append(lp(
        "ADMIN PREVIEW — not for distribution. Layout algorithm uses simplified row sweep "
        "(no tilt-angle ground-projection correction; module N-S footprint = module height). "
        "BOM quantities are preliminary estimates. Verify all figures before use in proposals or EPC.",
        nte))
    story.append(Spacer(1, 0.1*cm))
    story.append(lp(
        "Generated by LayoutIQ — PVMath Solar Site Intelligence Platform | pvmath.com", nte))

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ─────────────────────────────────────────────────────────────────────────────
# UI — INPUTS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="liq-section">📁 Step 1 — Site Boundary</div>', unsafe_allow_html=True)

input_method = st.radio(
    "Polygon input method",
    ["Upload KML file", "Upload DXF file", "Paste lat/lon coordinates"],
    horizontal=True, label_visibility="collapsed"
)

polygon_latlons = None
polygon_source  = ""

if input_method == "Upload KML file":
    kml_file = st.file_uploader("Upload site boundary (.kml)", type=["kml", "kmz"])
    if kml_file:
        pts = parse_kml(kml_file.read())
        if pts:
            polygon_latlons = pts
            polygon_source  = kml_file.name
            st.success(f"✅ Polygon loaded — {len(pts)} vertices")
        else:
            st.error("Could not extract polygon from KML. Check the file has a polygon, not just a path.")

elif input_method == "Upload DXF file":
    dxf_file = st.file_uploader("Upload site boundary (.dxf)", type=["dxf"])
    st.info("ℹ️ DXF polygon must be in local metres (UTM or similar projected CRS). "
            "For lat/lon DXF, use the paste method instead.")
    if dxf_file:
        pts, is_local = parse_dxf(dxf_file.read())
        if pts:
            # DXF is local metres — use directly (treat Y as lat-proxy, X as lon-proxy)
            polygon_latlons = pts  # will be treated as local coords
            polygon_source  = dxf_file.name
            st.success(f"✅ Polygon loaded — {len(pts)} points")
        else:
            st.error("Could not extract LWPOLYLINE from DXF.")

else:
    paste_text = st.text_area(
        "Paste polygon coordinates (one lat,lon per line)",
        placeholder="48.1372, 11.5756\n48.1368, 11.5762\n48.1360, 11.5750\n...",
        height=140,
    )
    if paste_text.strip():
        pts = parse_pasted(paste_text)
        if pts:
            polygon_latlons = pts
            polygon_source  = "pasted coordinates"
            st.success(f"✅ {len(pts)} vertices parsed")
        else:
            st.error("Could not parse coordinates. Use 'lat,lon' format, one per line.")

# ── Module + row + inverter params ────────────────────────────────────────────
st.markdown('<div class="liq-section">⚙️ Step 2 — Module & Row Parameters</div>',
            unsafe_allow_html=True)

c1, c2 = st.columns(2)
with c1:
    st.markdown("**Module specification**")
    module_preset = st.selectbox("Module preset", list(MODULE_PRESETS.keys()))
    preset_vals   = MODULE_PRESETS[module_preset]

    if preset_vals:
        mod_h  = preset_vals["h"]
        mod_w  = preset_vals["w"]
        mod_wp = preset_vals["wp"]
        st.markdown(
            f"<div style='font-size:0.85rem;color:#5a5a7a;margin-top:0.2rem;'>"
            f"Height: <b>{mod_h} m</b> · Width: <b>{mod_w} m</b> · Power: <b>{mod_wp} Wp</b>"
            f"</div>", unsafe_allow_html=True
        )
    else:
        mc1, mc2, mc3 = st.columns(3)
        mod_h  = mc1.number_input("Height (m)", 1.5, 3.0, 2.094, 0.001, format="%.3f")
        mod_w  = mc2.number_input("Width (m)",  0.8, 1.5, 1.038, 0.001, format="%.3f")
        mod_wp = mc3.number_input("Power (Wp)", 200, 1000, 550, 5)

with c2:
    st.markdown("**Row configuration**")
    rc0, rc1 = st.columns(2)
    mounting_type = rc0.selectbox(
        "Mounting type",
        ["fixed_tilt", "sat"],
        format_func=lambda x: "Fixed Tilt" if x == "fixed_tilt" else "Single-Axis Tracker (SAT)",
    )
    is_tracker = (mounting_type == "sat")
    n_portrait = rc1.selectbox("Portrait rows (1P / 2P)", [1, 2],
                                format_func=lambda x: f"{x}P")

    rc2, rc3, rc4 = st.columns(3)
    if not is_tracker:
        azimuth = rc2.number_input("Azimuth (°)", 90.0, 270.0, 180.0, 1.0,
                                    help="180° = south-facing. Applies to fixed tilt only.")
    else:
        azimuth = 180.0
        rc2.markdown(
            "<div style='font-size:0.82rem;color:#7c3aed;margin-top:1.6rem;font-weight:600'>"
            "SAT — N-S axis (no azimuth)</div>", unsafe_allow_html=True
        )

    pitch_label = "Row pitch E-W (m)" if is_tracker else "Row pitch N-S (m)"
    pitch_help  = ("E-W distance between tracker row centrelines." if is_tracker
                   else "N-S front-to-front row spacing.")
    pitch   = rc3.number_input(pitch_label, 2.0, 20.0, 5.5 if is_tracker else 5.0, 0.1,
                                help=pitch_help)
    setback = rc4.number_input("Boundary setback (m)", 0.0, 50.0, 5.0, 0.5,
                                help="Inset from site boundary.")
    gap = st.number_input("Module gap within row (m)", 0.0, 0.1, 0.01, 0.005, format="%.3f",
                           help="Gap between modules along the row.")

st.markdown("---")
st.markdown("**Inverter & string configuration**")
ic1, ic2, ic3 = st.columns(3)
mps     = ic1.number_input("Modules per string",    8,  50, 28, 1)
spi     = ic2.number_input("Strings per inverter",  1,  50, 4, 1)
inv_ac  = ic3.number_input("Inverter AC power (kW)", 10.0, 5000.0, 100.0, 10.0)

project_name = st.text_input("Project name", placeholder="e.g. Regensburg North — 50 MWp",
                              value="")
if not project_name.strip():
    project_name = "LayoutIQ Project"

# ── Run ───────────────────────────────────────────────────────────────────────
st.markdown('<div class="liq-section">▶ Step 3 — Run Layout</div>', unsafe_allow_html=True)

row_ns_display = f"{n_portrait}P row width: {round(mod_h * n_portrait, 3)} m  |  "     \
                 f"Pitch: {pitch} m  |  Row gap: {round(pitch - mod_h * n_portrait, 2)} m"
st.markdown(f"<div style='font-size:0.85rem;color:#5a5a7a;margin-bottom:0.8rem;'>{row_ns_display}</div>",
            unsafe_allow_html=True)

_row_cross = mod_w * n_portrait if is_tracker else mod_h * n_portrait
if pitch <= _row_cross:
    st.error(f"⚠️ Pitch ({pitch} m) must be greater than row cross-section ({round(_row_cross,2)} m).")
    st.stop()

run_btn = st.button("📐 Generate Layout + BOM", type="primary",
                    disabled=(polygon_latlons is None))

if polygon_latlons is None and not run_btn:
    st.info("Upload or paste a site polygon to enable layout generation.")

# ─────────────────────────────────────────────────────────────────────────────
# COMPUTE + DISPLAY
# ─────────────────────────────────────────────────────────────────────────────
if run_btn and polygon_latlons:
    with st.spinner("Running layout algorithm…"):
        layout = run_layout(
            polygon_latlons,
            module_h=mod_h, module_w=mod_w,
            n_portrait=n_portrait,
            pitch=pitch, setback=setback,
            azimuth=azimuth,
            mounting_type=mounting_type,
            inter_gap=gap,
        )

    if layout is None:
        st.error("Layout failed — polygon too small after setback, or pitch larger than polygon N-S extent.")
        st.stop()

    # ── Key metrics ──────────────────────────────────────────────────────────
    dc_kwp = layout["total_modules"] * mod_wp / 1000
    st.markdown('<div class="liq-section">📊 Layout Results</div>', unsafe_allow_html=True)

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Total Modules",   f"{layout['total_modules']:,}")
    m2.metric("Total Rows",      str(layout["total_rows"]))
    m3.metric("DC Capacity",     f"{dc_kwp:,.0f} kWp")
    m4.metric("Site Area",       f"{layout['area_ha']} ha")
    m5.metric("Land Use",        f"{round(dc_kwp/1000/layout['area_ha'],3)} MWp/ha")
    m6.metric("Modules / ha",    f"{int(round(layout['total_modules']/layout['area_ha'])):,}")

    # ── Layout drawing ───────────────────────────────────────────────────────
    module_label = module_preset if module_preset != "Custom input" else f"Custom {mod_wp}Wp"
    chart_bytes  = make_layout_drawing(layout, project_name, mod_wp, azimuth)
    st.image(chart_bytes, use_container_width=True)

    # ── BOM ──────────────────────────────────────────────────────────────────
    st.markdown('<div class="liq-section">📋 Bill of Materials (Preliminary)</div>',
                unsafe_allow_html=True)
    bom = compute_bom(layout, mod_wp, n_portrait, mps, spi, inv_ac)

    bom_col1, bom_col2 = st.columns(2)
    bom_items = list(bom.items())
    half = math.ceil(len(bom_items) / 2)
    for key, val in bom_items[:half]:
        c_k, c_v = bom_col1.columns([1.4, 1])
        c_k.markdown(f"<div style='font-size:0.88rem;color:#5a5a7a;font-weight:600;'>{key}</div>",
                     unsafe_allow_html=True)
        c_v.markdown(f"<div style='font-size:0.88rem;font-weight:700;color:#1a1a2e;'>{val}</div>",
                     unsafe_allow_html=True)
    for key, val in bom_items[half:]:
        c_k, c_v = bom_col2.columns([1.4, 1])
        c_k.markdown(f"<div style='font-size:0.88rem;color:#5a5a7a;font-weight:600;'>{key}</div>",
                     unsafe_allow_html=True)
        c_v.markdown(f"<div style='font-size:0.88rem;font-weight:700;color:#1a1a2e;'>{val}</div>",
                     unsafe_allow_html=True)

    # ── Row-by-row table ─────────────────────────────────────────────────────
    with st.expander("Row-by-row breakdown"):
        rows_df_data = {
            "Row #":           list(range(1, len(layout["rows_data"]) + 1)),
            "Modules":         [r["n_modules"] for r in layout["rows_data"]],
            "Row length (m)":  [r["length_m"]  for r in layout["rows_data"]],
        }
        import pandas as pd
        st.dataframe(pd.DataFrame(rows_df_data), use_container_width=True, height=250)

    # ── PDF ──────────────────────────────────────────────────────────────────
    st.markdown("---")
    pdf_bytes = build_pdf(
        project_name, layout, bom, chart_bytes,
        module_label, mod_wp, n_portrait, pitch, setback, azimuth
    )
    safe = re.sub(r"[^\w\- ]", "", project_name).strip().replace(" ", "_")
    st.download_button(
        "📄 Download PDF Report",
        data=pdf_bytes,
        file_name=f"LayoutIQ_{safe}.pdf",
        mime="application/pdf",
        type="primary",
    )

    # ── Admin note ───────────────────────────────────────────────────────────
    st.markdown("""
    <div style="margin-top:1rem;padding:0.7rem 1rem;background:#f5f3ff;
                border-radius:8px;border-left:3px solid #7c3aed;
                font-size:0.82rem;color:#4c1d95;">
    <strong>Admin note:</strong>
    Row width = module height (no tilt-angle ground projection).
    Foundation posts, rails, clamps, and cable are engineering estimates (±20%).
    String/inverter counts assume uniform string length across all rows —
    partial strings at row ends are ceil-rounded.
    </div>
    """, unsafe_allow_html=True)
