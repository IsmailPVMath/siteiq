import streamlit as st
import numpy as np
import requests
import math
import io
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
    increment_usage, is_over_limit, remaining, FREE_LIMIT, STRIPE_LINK, PRICE_LABEL
)

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
    from shapely.geometry import shape, Point, Polygon as ShapelyPolygon
    from shapely.ops import unary_union
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

def generate_pdf_report(
    fname, lat_c, lon_c, area_ha, grid_spacing,
    z_min, z_max, z_range, mean_slope, max_slope,
    pct_over5, pct_over10,
    elev_img_buf, slope_img_buf,
    verdict_label, verdict_detail,
    project_name="", country=""
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
                                  fontSize=20, textColor=colors.white,
                                  alignment=TA_CENTER, spaceAfter=2)
    sub_style   = ParagraphStyle("sub", fontName="Helvetica",
                                  fontSize=9, textColor=colors.HexColor("#b0c4de"),
                                  alignment=TA_CENTER)
    hdr_style   = ParagraphStyle("hdr", fontName="Helvetica-Bold",
                                  fontSize=11, textColor=MID_BLUE,
                                  spaceBefore=6, spaceAfter=3)
    body_style  = ParagraphStyle("body", fontName="Helvetica",
                                  fontSize=9, textColor=colors.HexColor("#333333"),
                                  leading=13)

    story = []

    header_tbl = Table([[Paragraph("TopoIQ — Terrain Intelligence Report", title_style)],
                         [Paragraph(f"by PVMath · pvmath.com · Generated {datetime.now().strftime('%d %b %Y')}", sub_style)]],
                        colWidths=[usable])
    header_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), DARK_BLUE),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING",   (0,0), (-1,-1), 12),
        ("ROUNDEDCORNERS", [6]),
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

    story.append(Paragraph("Visual Maps", hdr_style))
    img_w = (usable - 6*mm) / 2

    imgs = []
    for buf_img in [elev_img_buf, slope_img_buf]:
        if buf_img:
            buf_img.seek(0)
            imgs.append(RLImage(buf_img, width=img_w, height=img_w * 0.82))
        else:
            imgs.append(Spacer(img_w, img_w * 0.82))

    img_tbl = Table([imgs], colWidths=[img_w, img_w], hAlign="CENTER")
    img_tbl.setStyle(TableStyle([
        ("LEFTPADDING",  (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 3),
        ("TOPPADDING",   (0,0), (-1,-1), 0),
        ("BOTTOMPADDING",(0,0), (-1,-1), 0),
    ]))
    story.append(img_tbl)
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
        "Generated by TopoIQ · PVMath (pvmath.com) · contact@pvmath.de",
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


st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=DM+Serif+Display&display=swap" rel="stylesheet">
<style>
    html, body, [class*="css"] {
        font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif !important;
        font-size: 15px !important;
    }
    p, li, label, span, div { font-size: 0.97rem; line-height: 1.65; }
    [data-testid="stMarkdown"] p { font-size: 0.97rem; }
    [data-testid="stRadio"] label { font-size: 0.97rem !important; }
    [data-testid="stSelectbox"] label, [data-testid="stTextInput"] label,
    [data-testid="stNumberInput"] label { font-size: 0.95rem !important; font-weight: 600; color: #1a2a4a; }
    [data-testid="stMetric"] label { font-size: 0.8rem !important; }
    [data-testid="stMetric"] [data-testid="stMetricValue"] { font-size: 1.5rem !important; font-weight: 700; }
    footer { visibility: hidden !important; height: 0 !important; }
    #MainMenu { visibility: hidden !important; }
    header { visibility: hidden !important; }
    [data-testid="stToolbar"]       { display: none !important; }
    [data-testid="stDeployButton"]  { display: none !important; }
    [data-testid="stStatusWidget"]  { display: none !important; }
    [data-testid="stDecoration"]    { display: none !important; }
    #stDecoration                   { display: none !important; }
    [class*="viewerBadge"]          { display: none !important; }
    [class*="StatusWidget"]         { display: none !important; }
    [class*="deployButton"]         { display: none !important; }
    [class*="styles_viewerBadge"]   { display: none !important; }
    iframe[title="streamlitApp"]    { display: none !important; }
    [style*="position: fixed"][style*="bottom"][style*="right"],
    [style*="position:fixed"][style*="bottom"][style*="right"] { display: none !important; }
    </style>
    <script>
    (function() {
      function killBadge() {
        document.querySelectorAll('*').forEach(function(el) {
          try {
            var s = window.getComputedStyle(el);
            var cl = el.className ? el.className.toString().toLowerCase() : '';
            if (
              (s.position === 'fixed' && parseInt(s.bottom) >= 0 && parseInt(s.right) >= 0 && el.tagName !== 'BODY') ||
              cl.includes('badge') || cl.includes('viewer')
            ) {
              el.style.setProperty('display', 'none', 'important');
              el.style.setProperty('visibility', 'hidden', 'important');
            }
          } catch(e) {}
        });
      }
      killBadge();
      new MutationObserver(killBadge).observe(document.documentElement, {childList:true, subtree:true});
    })();
    </script>
    <style>

    .pvmath-header {
        display: flex; align-items: center; gap: 0.75rem;
        padding: 0.5rem 0 1rem 0; border-bottom: 1px solid #e8ede8; margin-bottom: 1.2rem;
    }
    .pvmath-logo-mark {
        width: 40px; height: 40px; border-radius: 10px;
        background: linear-gradient(135deg, #1565c0, #42a5f5);
        display: flex; align-items: center; justify-content: center; flex-shrink: 0;
    }
    .pvmath-app-name { font-size: 1.75rem; font-weight: 800; letter-spacing: -0.02em; color: #1565c0; }
    .pvmath-app-sub  { font-size: 0.88rem; color: #888; font-weight: 500; }
    .pvmath-tagline  { font-size: 0.95rem; color: #5a7a5a; margin-top: 0.15rem; font-weight: 400; line-height: 1.5; }

    .section-hdr {
        font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.13em; color: #1565c0;
        display: flex; align-items: center; gap: 0.5rem;
        margin: 1.4rem 0 0.75rem 0; padding-bottom: 0.45rem;
        border-bottom: 2px solid #dce8f5;
    }

    .accuracy-card {
        background: #f0f7ff; border: 1px solid #c5daf5;
        border-left: 3px solid #1565c0;
        border-radius: 8px; padding: 0.9rem 1.1rem; margin-top: 0.8rem;
        font-size: 0.82rem;
    }
    .accuracy-card h4 { color: #1565c0; margin-bottom: 0.35rem; font-size: 0.85rem; font-weight: 700; }
    .accuracy-card p  { color: #334; margin: 0.12rem 0; line-height: 1.5; }

    div[data-testid="metric-container"] {
        background: #fff; border: 1px solid #e2ede2;
        border-radius: 10px; padding: 1rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.04);
    }

    div[data-testid="stButton"] > button {
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important; letter-spacing: 0.01em;
        border-radius: 8px !important;
    }
    div[data-testid="stButton"] > button[kind="primary"] {
        background: linear-gradient(135deg, #1d9e52, #145f34) !important;
        border: none !important; color: #fff !important;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #27ae60, #1d9e52) !important;
        box-shadow: 0 0 20px rgba(29,158,82,0.3) !important;
    }

    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        color: #1d9e52 !important; border-bottom-color: #1d9e52 !important; font-weight: 700 !important;
    }
    div[data-testid="stTabs"] button[role="tab"] { font-weight: 500 !important; }

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

    section[data-testid="stSidebar"] { background: #f5f7f5 !important; }
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

def fetch_terrarium_tile(x, y, zoom):
    url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{zoom}/{x}/{y}.png"
    r = requests.get(url, timeout=15)
    if r.status_code != 200:
        return None, None
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    arr = np.array(img, dtype=np.float32)
    elev = arr[:, :, 0] * 256.0 + arr[:, :, 1] + arr[:, :, 2] / 256.0 - 32768.0
    lat_n, lon_w = tile2deg(x, y, zoom)
    lat_s, lon_e = tile2deg(x + 1, y + 1, zoom)
    bounds = {"lat_n": lat_n, "lat_s": lat_s, "lon_w": lon_w, "lon_e": lon_e}
    return elev, bounds


def get_dem_for_bbox(south, north, west, east, zoom=14):
    x_min, y_min = deg2tile(north, west, zoom)
    x_max, y_max = deg2tile(south, east, zoom)
    tiles = []
    total = (x_max - x_min + 1) * (y_max - y_min + 1)
    prog = st.progress(0, text="Downloading terrain tiles…")
    count = 0
    for ty in range(y_min, y_max + 1):
        row = []
        for tx in range(x_min, x_max + 1):
            elev, bounds = fetch_terrarium_tile(tx, ty, zoom)
            if elev is not None:
                row.append((elev, bounds))
            count += 1
            prog.progress(count / total, text=f"Downloading tile {count}/{total}…")
        if row:
            tiles.append(row)
    prog.empty()
    if not tiles:
        return None, None, None, None, None

    mosaic_rows = []
    for row in tiles:
        mosaic_rows.append(np.concatenate([t[0] for t in row], axis=1))
    mosaic = np.concatenate(mosaic_rows, axis=0)

    lat_n_all = tiles[0][0][1]["lat_n"]
    lat_s_all = tiles[-1][0][1]["lat_s"]
    lon_w_all = tiles[0][0][1]["lon_w"]
    lon_e_all = tiles[0][-1][1]["lon_e"]
    return mosaic, lat_n_all, lat_s_all, lon_w_all, lon_e_all


def resample_to_grid(mosaic, lat_n, lat_s, lon_w, lon_e,
                     polygon_coords, grid_m=5.0):
    h, w = mosaic.shape
    lat_c = (lat_n + lat_s) / 2
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat_c))

    step_lat = grid_m / m_per_deg_lat
    step_lon = grid_m / m_per_deg_lon

    if polygon_coords:
        lons_p = [c[0] for c in polygon_coords]
        lats_p = [c[1] for c in polygon_coords]
        p_w, p_e = min(lons_p), max(lons_p)
        p_s, p_n = min(lats_p), max(lats_p)
    else:
        p_w, p_e, p_s, p_n = lon_w, lon_e, lat_s, lat_n

    grid_lons = np.arange(p_w, p_e, step_lon)
    grid_lats = np.arange(p_n, p_s, -step_lat)
    X, Y = np.meshgrid(grid_lons, grid_lats)

    def sample(lon, lat):
        col = (lon - lon_w) / (lon_e - lon_w) * (w - 1)
        row = (lat_n - lat) / (lat_n - lat_s) * (h - 1)
        col = np.clip(col, 0, w - 2).astype(int)
        row = np.clip(row, 0, h - 2).astype(int)
        return mosaic[row, col]

    Z = sample(X, Y)

    if HAS_SHAPELY and polygon_coords and len(polygon_coords) >= 3:
        poly = ShapelyPolygon(polygon_coords)
        mask = np.array([
            [poly.contains(Point(X[r, c], Y[r, c]))
             for c in range(X.shape[1])]
            for r in range(X.shape[0])
        ])
        Z = np.where(mask, Z, np.nan)

    return X, Y, Z


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


# ─── KML/KMZ parser ───────────────────────────────────────────────────────────

def _parse_kml_coords(text):
    pairs = []
    for tok in text.strip().split():
        parts = tok.split(",")
        if len(parts) >= 2:
            try:
                pairs.append((float(parts[0]), float(parts[1])))
            except ValueError:
                pass
    return pairs


def parse_kml_all_polygons(raw_bytes):
    import xml.etree.ElementTree as ET2
    NS = "http://www.opengis.net/kml/2.2"

    try:
        root2 = ET2.fromstring(raw_bytes)
    except Exception:
        return {}

    results = {}

    def coords_from_el(el):
        c = el.find(f"{{{NS}}}coordinates")
        if c is None:
            c = el.find("coordinates")
        return _parse_kml_coords(c.text) if (c is not None and c.text) else []

    for pm in root2.iter(f"{{{NS}}}Placemark"):
        name_el = pm.find(f"{{{NS}}}name")
        name = name_el.text.strip() if (name_el is not None and name_el.text) else "Unnamed"

        for poly_el in pm.iter(f"{{{NS}}}Polygon"):
            outer = poly_el.find(f".//{{{NS}}}outerBoundaryIs/{{{NS}}}LinearRing")
            if outer is not None:
                pts = coords_from_el(outer)
            else:
                pts = coords_from_el(poly_el)
            if len(pts) >= 3:
                key = f"Polygon: {name}" if name not in results else f"Polygon: {name}_{len(results)}"
                results[key] = pts

        for lr in pm.iter(f"{{{NS}}}LinearRing"):
            if pm.find(f".//{{{NS}}}Polygon") is not None:
                continue
            pts = coords_from_el(lr)
            if len(pts) >= 3:
                key = f"Ring: {name}" if name not in results else f"Ring: {name}_{len(results)}"
                results[key] = pts

        for ls in pm.iter(f"{{{NS}}}LineString"):
            pts = coords_from_el(ls)
            if len(pts) >= 3:
                first, last = pts[0], pts[-1]
                dist = math.sqrt((first[0]-last[0])**2 + (first[1]-last[1])**2)
                if dist < 0.001:
                    key = f"Line: {name}" if name not in results else f"Line: {name}_{len(results)}"
                    results[key] = pts

    if not results:
        for pm in root2.iter("Placemark"):
            name_el = pm.find("name")
            name = name_el.text.strip() if (name_el is not None and name_el.text) else "Unnamed"
            for poly_el in pm.iter("Polygon"):
                outer = poly_el.find(".//outerBoundaryIs/LinearRing")
                c_el = outer.find("coordinates") if outer is not None else poly_el.find("coordinates")
                if c_el is not None and c_el.text:
                    pts = _parse_kml_coords(c_el.text)
                    if len(pts) >= 3:
                        results[f"Polygon: {name}"] = pts

    return results


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
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            kml_name = next((n for n in z.namelist() if n.endswith(".kml")), None)
            if kml_name:
                raw = z.read(kml_name)
        return raw, "kml"
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

_siq = {k: st.session_state.get(k) for k in
        ["siteiq_project_name", "siteiq_country", "siteiq_lat", "siteiq_lon", "siteiq_area_ha"]}

if _siq["siteiq_lat"] and _siq["siteiq_lon"]:
    _pname   = _siq["siteiq_project_name"] or "Unnamed Project"
    _country = _siq["siteiq_country"] or ""
    _label   = f"{_pname}" + (f" · {_country}" if _country else "")
    st.markdown(
        f'<div style="background:linear-gradient(90deg,#1565c0,#0d47a1);'
        f'border-radius:10px;padding:0.7rem 1.1rem;margin-bottom:0.8rem;'
        f'display:flex;align-items:center;justify-content:space-between;">'
        f'<span style="color:white;font-size:0.92rem;">'
        f'<i class="fa-solid fa-link" style="margin-right:0.5rem;"></i>'
        f'<b>SiteIQ project available:</b> {_label} &nbsp;'
        f'<span style="opacity:0.75;font-size:0.82rem;">({_siq["siteiq_lat"]:.4f}°, {_siq["siteiq_lon"]:.4f}°)</span>'
        f'</span></div>',
        unsafe_allow_html=True
    )
    if st.button("📥 Load this site into TopoIQ", use_container_width=True):
        st.session_state["topo_center"]      = [_siq["siteiq_lat"], _siq["siteiq_lon"]]
        st.session_state["topo_zoom"]        = 14
        st.session_state["topo_project_name"] = _pname
        st.session_state["topo_country"]      = _country
        st.rerun()

topo_project_name = st.session_state.get("topo_project_name", "")
topo_country      = st.session_state.get("topo_country", "")

with st.expander("✏️ Set project name for report", expanded=not bool(topo_project_name)):
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

    input_method = st.radio("Input method", [
        "✏️ Draw Site Boundary on Map",
        "📁 Upload KML / KMZ / DXF / DWG",
    ], horizontal=True)

    polygon_coords = None

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
                        headers={"User-Agent": "TopoIQ/1.0 (pvmath.com; contact@pvmath.de)"},
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
                lat_in = st.text_input("Latitude", placeholder="e.g. 26.8467",
                                       key="coord_lat")
            with c2:
                lon_in = st.text_input("Longitude", placeholder="e.g. 80.9462",
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
            st.success(f"✅ Site boundary captured — {len(polygon_coords)-1} vertices")
        else:
            st.caption("Draw your site boundary on the map above to enable analysis.")

    else:
        f = st.file_uploader(
            "Upload boundary file",
            type=["kml", "kmz", "dxf", "dwg"],
            help="KML / KMZ from Google Earth · DXF or DWG from any CAD software"
        )
        if f:
            raw, ftype = load_boundary_file(f)

            if ftype == "dwg_unsupported":
                st.warning(
                    "**DWG file could not be read directly.**\n\n"
                    "In your CAD software: **File → Save As → AutoCAD DXF** (takes ~5 seconds). "
                    "Then re-upload the `.dxf` file here."
                )
                all_polys = {}
            elif ftype in ("kml",):
                all_polys = parse_kml_all_polygons(raw)
            elif ftype in ("dxf", "dwg_ok"):
                all_polys = parse_dxf_polygons(raw)
            else:
                all_polys = {}

            if not all_polys:
                st.error("No closed polygon found in file. Check the file contains a site boundary polyline or polygon.")
            elif len(all_polys) == 1:
                polygon_coords = list(all_polys.values())[0]
                st.success(f"Boundary loaded — {len(polygon_coords)} vertices")
            else:
                st.info(f"Found {len(all_polys)} polygons/boundaries in file. Select the site boundary:")
                chosen = st.selectbox("Select boundary", list(all_polys.keys()))
                polygon_coords = all_polys[chosen]
                st.success(f"Selected: **{chosen}** — {len(polygon_coords)} vertices")

            if polygon_coords:
                lons = [c[0] for c in polygon_coords]
                lats = [c[1] for c in polygon_coords]
                m2 = folium.Map(location=[np.mean(lats), np.mean(lons)],
                                zoom_start=13,
                                tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                                attr="Google Satellite")
                folium.Polygon(
                    locations=[(c[1], c[0]) for c in polygon_coords],
                    color="#42a5f5", fill=True, fill_opacity=0.25, weight=2
                ).add_to(m2)
                st_folium(m2, width=None, height=300, returned_objects=[])

    st.markdown('<div class="section-hdr" style="margin-top:1rem;"><i class="fa-solid fa-sliders" style="color:#1565c0;"></i> Settings</div>', unsafe_allow_html=True)
    sc1, sc2 = st.columns(2)
    grid_spacing = sc1.selectbox("Grid spacing", [5, 3, 10], index=0,
                                  help="5m = preliminary design, 3m = detailed study")
    contour_minor = sc2.selectbox("Minor contour (m)", [0.5, 0.25, 1.0], index=0)
    contour_major = st.selectbox("Major contour (m)", [1.0, 2.0, 5.0], index=0)

    _topo_user = st.session_state.get("pvm_user_id", "guest")
    _topo_left = remaining(_topo_user, "topoiq")

    if is_over_limit(_topo_user, "topoiq"):
        st.markdown(f"""
        <div style="background:#fff;border:1.5px solid #e2ede2;border-radius:14px;
                    padding:1.8rem 1.6rem;text-align:center;margin-top:0.5rem;
                    font-family:'Inter',sans-serif;">
          <div style="font-size:2rem;margin-bottom:0.5rem;">🔒</div>
          <div style="font-size:1.2rem;font-weight:800;color:#1565c0;margin-bottom:0.4rem;">
            Free Trial Complete
          </div>
          <div style="color:#555;font-size:0.88rem;margin-bottom:1.2rem;line-height:1.6;">
            You've used all <b>{FREE_LIMIT} free analyses</b> in TopoIQ.<br>
            Upgrade to run unlimited terrain extractions.
          </div>
          <a href="{STRIPE_LINK}" target="_blank"
             style="display:inline-block;background:linear-gradient(135deg,#1d9e52,#145f34);
                    color:#fff;font-weight:700;font-size:0.95rem;padding:0.75rem 2rem;
                    border-radius:9px;text-decoration:none;letter-spacing:0.01em;">
            Upgrade — {PRICE_LABEL} →
          </a>
          <div style="margin-top:1rem;font-size:0.78rem;color:#999;">
            Questions? <a href="mailto:contact@pvmath.de" style="color:#1d9e52;">contact@pvmath.de</a>
          </div>
        </div>
        """, unsafe_allow_html=True)
        run = False
    else:
        if _topo_left <= 1:
            st.warning(f"⚠️ {_topo_left} free analysis remaining after this run.")
        run = st.button("⛰ Run Terrain Analysis", type="primary",
                        use_container_width=True,
                        disabled=(polygon_coords is None))
        if polygon_coords is None:
            st.caption("Draw or upload a site boundary to enable analysis.")

# ─── Results ──────────────────────────────────────────────────────────────────
with right:
    if run and polygon_coords:
        increment_usage(st.session_state.get("pvm_user_id", "guest"), "topoiq")
        lons_p = [c[0] for c in polygon_coords]
        lats_p = [c[1] for c in polygon_coords]
        south, north = min(lats_p) - 0.001, max(lats_p) + 0.001
        west,  east  = min(lons_p) - 0.001, max(lons_p) + 0.001
        lat_c = (south + north) / 2
        lon_c = (west  + east)  / 2

        m_per_deg_lat = 111320.0
        m_per_deg_lon = 111320.0 * math.cos(math.radians(lat_c))
        area_ha = ((north - south) * m_per_deg_lat *
                   (east  - west)  * m_per_deg_lon) / 10000

        with st.spinner("Fetching satellite terrain data…"):
            mosaic, lat_n, lat_s, lon_w, lon_e = get_dem_for_bbox(
                south, north, west, east, zoom=14
            )

        if mosaic is None:
            st.error("Could not fetch terrain data. Check your internet connection.")
            st.stop()

        with st.spinner(f"Processing {grid_spacing}m grid…"):
            X, Y, Z = resample_to_grid(
                mosaic, lat_n, lat_s, lon_w, lon_e,
                polygon_coords, grid_m=float(grid_spacing)
            )
            slope = compute_slope(Z, float(grid_spacing))

        z_valid = Z[~np.isnan(Z)]
        s_valid = slope[~np.isnan(slope) & ~np.isnan(Z)]

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
            f'🔢 <b>{len(z_valid):,}</b> grid points at <b>{grid_spacing} m</b> &nbsp;·&nbsp; '
            f'⚠️ <b>{pct_over5:.0f}%</b> of site &gt;5% slope &nbsp;·&nbsp; '
            f'🔴 <b>{pct_over10:.0f}%</b> &gt;10% slope'
            f'</div>',
            unsafe_allow_html=True
        )

        st.divider()
        st.markdown('<div class="section-hdr"><i class="fa-solid fa-layer-group" style="color:#1565c0;"></i> Visual Maps</div>', unsafe_allow_html=True)

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors

        map_col1, map_col2 = st.columns(2)

        with map_col1:
            Zm = np.ma.masked_invalid(np.flipud(Z))
            fig, ax = plt.subplots(figsize=(6, 5))
            fig.patch.set_facecolor("#0e1117")
            ax.set_facecolor("#0e1117")
            im = ax.imshow(Zm, cmap="RdYlGn_r", interpolation="bilinear", aspect="auto")
            cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label("Elevation (m)", color="white", fontsize=9)
            cbar.ax.yaxis.set_tick_params(color="white", labelsize=8)
            plt.setp(cbar.ax.yaxis.get_ticklabels(), color="white")
            ax.set_title(f"Elevation · {grid_spacing}m grid", color="white", fontsize=10, pad=6)
            ax.set_xticks([]); ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_edgecolor("#333")
            plt.tight_layout(pad=0.5)
            pdf_elev_buf = io.BytesIO()
            fig.savefig(pdf_elev_buf, format="png", dpi=150, bbox_inches="tight", facecolor="#0e1117")
            pdf_elev_buf.seek(0); plt.close(fig)
            st.image(pdf_elev_buf, use_container_width=True)

        with map_col2:
            if HAS_SCIPY:
                dy, dx = np.gradient(Z, grid_spacing, grid_spacing)
                slope_pct = np.sqrt(dx**2 + dy**2) * 100
                Sm = np.ma.masked_invalid(np.flipud(slope_pct))
                fig2, ax2 = plt.subplots(figsize=(6, 5))
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
                cbar2 = fig2.colorbar(im2, ax=ax2, fraction=0.046, pad=0.04)
                cbar2.set_label("Slope (%)", color="white", fontsize=9)
                cbar2.ax.yaxis.set_tick_params(color="white", labelsize=8)
                plt.setp(cbar2.ax.yaxis.get_ticklabels(), color="white")
                ax2.set_title(f"Slope · {grid_spacing}m grid  (green<3%, red>10%)",
                              color="white", fontsize=10, pad=6)
                ax2.set_xticks([]); ax2.set_yticks([])
                for spine in ax2.spines.values():
                    spine.set_edgecolor("#333")
                plt.tight_layout(pad=0.5)
                pdf_slope_buf = io.BytesIO()
                fig2.savefig(pdf_slope_buf, format="png", dpi=150, bbox_inches="tight", facecolor="#0e1117")
                pdf_slope_buf.seek(0); plt.close(fig2)
                st.image(pdf_slope_buf, use_container_width=True)
            else:
                pdf_slope_buf = None
                st.info("Install scipy for slope map.")

        st.divider()
        st.markdown('<div class="section-hdr"><i class="fa-solid fa-download" style="color:#1565c0;"></i> Download Outputs</div>', unsafe_allow_html=True)
        fname = f"TopoIQ_{lat_c:.3f}_{lon_c:.3f}_{grid_spacing}m"

        with st.spinner("Generating PDF report…"):
            pdf_slope_buf_for_pdf = pdf_slope_buf if HAS_SCIPY else None
            pdf_bytes = generate_pdf_report(
                fname=fname, lat_c=lat_c, lon_c=lon_c,
                area_ha=area_ha, grid_spacing=grid_spacing,
                z_min=float(z_valid.min()), z_max=float(z_valid.max()),
                z_range=float(z_valid.max()-z_valid.min()),
                mean_slope=mean_slope, max_slope=float(s_valid.max()),
                pct_over5=pct_over5, pct_over10=pct_over10,
                elev_img_buf=pdf_elev_buf,
                slope_img_buf=pdf_slope_buf_for_pdf,
                verdict_label=verdict_label,
                verdict_detail=verdict_detail,
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
          <p><strong>Native resolution:</strong> ~2.4m per pixel at zoom 14</p>
          <p><strong>Output grid:</strong> {grid_spacing}m resampled</p>
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
            (wc1, "#1a2a4a", "#0f1e38", "#2a4080", "#5b9bd5",
             "SATELLITE DEM", "Copernicus GLO-30 · ~2.4m resolution · Global coverage"),
            (wc2, "#1a3a2a", "#0f2a1e", "#2a6040", "#4caf82",
             "CIVIL 3D READY", "LandXML TIN surface · import directly, no conversion"),
            (wc1, "#2a2a1a", "#1e1e0f", "#5a5a20", "#d4c44a",
             "DXF CONTOURS", f"Major & minor contour lines · configurable intervals"),
            (wc2, "#2a1a3a", "#1e0f2a", "#5a3a80", "#a87fd4",
             "XYZ POINT CLOUD", "Easting / Northing / Elevation CSV for any tool"),
            (wc1, "#1a2a3a", "#0a1828", "#1a4a6a", "#4ab0d4",
             "SLOPE ANALYSIS", "Mean slope · % area over threshold · tracker suitability"),
            (wc2, "#2a1a1a", "#1e0f0f", "#6a2a2a", "#d47a4a",
             "ACCURACY REPORT", "Source · resolution · RMSE · vegetation warnings"),
        ]
        for _col, _bg1, _bg2, _bd, _tc, _title, _desc in _wcards:
            _col.markdown(
                f'<div style="background:linear-gradient(135deg,{_bg1},{_bg2});'
                f'border:1px solid {_bd};border-radius:10px;padding:1rem;margin-bottom:0.75rem;">'
                f'<div style="color:{_tc};font-weight:700;font-size:0.9rem;">{_title}</div>'
                f'<div style="color:#ccc;font-size:0.78rem;margin-top:0.3rem;">{_desc}</div>'
                f'</div>',
                unsafe_allow_html=True
            )
