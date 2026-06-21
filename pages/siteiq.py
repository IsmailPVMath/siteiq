import streamlit as st
import requests
import pandas as pd
import altair as alt
import math
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
import folium
from pvmath_auth import (
    show_paywall,
    increment_usage, is_over_limit, remaining, FREE_LIMIT, UPGRADE_CONTACT,
    get_plan, plan_limit, plan_label, limit_reached_message,
    prepared_by_line, module_confidence_label,
)
from pvmath_styles import inject_styles
from pvmath_help import help_caption
from pvmath_kml import filter_boundary_list
from pvmath_geocode import reverse_geocode, format_coords, resolve_location_label, pdf_escape
from pvmath_topo_cache import resolve_terrain_for_siteiq, get_topo_cache, topo_cache_valid_for_siteiq
from pvmath_screening_library import (
    calculate_pvmath_score,
    get_verdict_from_score,
    build_screening_record,
    save_site_screening_result,
    get_global_benchmark_summary,
)
from pvmath_capacity import (
    screening_capacity,
    format_mwp_range,
    format_mwh_range,
    format_capacity_rating,
    capacity_basis_sentence,
    capacity_footnote_global,
)
from pvmath_yield import (
    get_solar_data,
    fetch_analysis_reference,
    profile_description,
    yield_cross_ref_siteiq_html,
    yield_cross_ref_pdf_text,
    PROFILE_SCREENING,
    SCREENING_LOSS_PCT,
)
from pvmath_pdf import (
    SITEIQ_DISCLAIMER_BODY,
    append_pdf_disclaimer,
    append_pdf_footer,
    strip_pdf_label,
)

# Shared rating legend — UI expander + PDF must stay in sync
SITEIQ_RATING_LEGEND_MD = """
| Rating | Meaning | Action |
|--------|---------|--------|
| ✅ Excellent / Good | Parameter within ideal range | Proceed — no major concerns |
| ⚠️ Acceptable | Feasible with constraints | Proceed with attention to this factor |
| ⚠️ Challenging | Near viability limit — significant effort | Detailed study mandatory |
| ❌ Critical | Exceeds viability threshold | High risk — reconsider site or system type |
| ⚠️ Indicative (slope) | Sparse OpenTopoData sample — quality tag reflects the sample, not confirmed site-wide terrain | Run **TopoIQ** before bankable use; overall verdict uses sample quality, not a blanket downgrade |
| ⚠️ Data unavailable | Solar or terrain data could not be retrieved | Retry or check API coverage for this location |
| — (capacity / output) | Screening MWp DC band from area × density @ GCR | Indicative only — confirm with layout / bankable study |
| ✅ EXCELLENT (overall) | All key parameters in ideal range | Proceed to detailed feasibility study |
| ✅ VERY GOOD (overall) | Strong site — one parameter good, one excellent | Proceed to detailed feasibility study |
| ✅ GOOD (overall) | Strong site with at most one moderate factor | Proceed — address noted constraint in detailed design |
| ⚠️ ACCEPTABLE (overall) | Viable with noted constraints | Address constraints in detailed design |
| ⚠️ CHALLENGING (overall) | Multiple moderate concerns | Detailed study mandatory before commitment |
| ❌ CRITICAL (overall) | One or more parameters exceed threshold | High risk — reconsider site or system type |
| 🟢 Low flood risk | Elevated terrain — flood exposure likely low | Verify at local flood portal |
| 🟡 Low-Moderate risk | Moderate terrain — check watercourse proximity | Cross-check official flood maps |
| 🟠 Moderate risk | Low-lying terrain — flood exposure possible | Manual flood check required |
| 🔴 High flood risk | Very low elevation — high flood exposure | Official flood zone study required |
"""
from streamlit_folium import st_folium
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.graphics import renderPDF
from reportlab.lib.units import cm

# ── User ID ──
_username = st.session_state.get("pvm_user_id", "guest")

# ─── Styling ──────────────────────────────────────────────────────────────────
inject_styles(accent="#1d9e52", accent_light="#e2ede2")

st.markdown("""
<style>

    /* ── Header ── */
    .pvmath-header {
        display: flex; align-items: center; gap: 0.75rem;
        padding: 0.5rem 0 1rem 0; border-bottom: 1px solid #e8ede8; margin-bottom: 1.2rem;
    }
    .pvmath-logo-mark {
        width: 40px; height: 40px; border-radius: 10px;
        background: linear-gradient(135deg, #1a5c2e, #1d9e52);
        display: flex; align-items: center; justify-content: center; flex-shrink: 0;
    }
    .pvmath-app-name { font-size: 1.75rem; font-weight: 800; letter-spacing: -0.02em; color: #0d1a0d; }
    .pvmath-app-sub  { font-size: 0.88rem; color: #4a6a4a; font-weight: 600; }
    .pvmath-tagline  { font-size: 0.97rem; color: #2a4a2a; margin-top: 0.15rem; font-weight: 500; line-height: 1.6; }

    /* ── Section headers ── */
    .section-hdr {
        font-size: 0.72rem; font-weight: 800; text-transform: uppercase;
        letter-spacing: 0.14em; color: #1d9e52;
        display: flex; align-items: center; gap: 0.5rem;
        margin: 1.6rem 0 0.85rem 0; padding-bottom: 0.5rem;
        border-bottom: 2.5px solid #d4e8d4;
    }
    /* ── Result value text ── */
    .result-label { font-size: 0.78rem; color: #1d9e52; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; }
    .result-value { font-size: 1.5rem; font-weight: 800; color: #0d1a0d; line-height: 1.15; letter-spacing: -0.02em; }
    .result-unit  { font-size: 0.88rem; font-weight: 500; color: #3a5a3a; margin-left: 0.2rem; }

    /* ── Metric cards ── */
    div[data-testid="metric-container"] {
        background: #fff; border: 1.5px solid #d4e8d4;
        border-radius: 12px; padding: 1.1rem;
        box-shadow: 0 1px 6px rgba(0,0,0,0.05);
    }
    .metric-card {
        background: #fff; border: 1.5px solid #d4e8d4;
        border-radius: 12px; padding: 0.95rem 0.85rem 0.9rem;
        box-shadow: 0 1px 6px rgba(0,0,0,0.05);
        min-height: 128px;
        height: 100%;
        display: flex;
        flex-direction: column;
        box-sizing: border-box;
    }
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.75rem;
        margin: 0.6rem 0 0.85rem 0;
    }
    @media (max-width: 960px) {
        .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    .metric-card .mc-icon { font-size: 1rem; line-height: 1; flex-shrink: 0; }
    .metric-card .mc-label {
        font-size: 0.78rem;
        font-weight: 800;
        color: #1a3a1a;
        letter-spacing: 0.03em;
        margin-top: 0.45rem;
        line-height: 1.25;
        min-height: 2.5em;
    }
    .metric-card .mc-value-row {
        margin-top: auto;
        padding-top: 0.35rem;
    }
    .metric-card .mc-number {
        display: block;
        font-size: 1.42rem;
        font-weight: 800;
        color: #0d1a0d;
        line-height: 1.1;
        letter-spacing: -0.02em;
        white-space: nowrap;
    }
    .metric-card .mc-unit {
        display: block;
        margin-top: 0.2rem;
        font-size: 0.72rem;
        font-weight: 600;
        color: #5a7a5a;
        letter-spacing: 0.03em;
        white-space: nowrap;
    }
    .siq-screening-notes {
        background: #f8faf8;
        border: 1px solid #dce8dc;
        border-left: 3px solid #b8a040;
        border-radius: 8px;
        padding: 0.6rem 0.85rem 0.65rem;
        margin: 0.25rem 0 1rem 0;
        font-size: 0.78rem;
        color: #3a5a3a;
        line-height: 1.5;
    }
    .siq-screening-notes .siq-notes-kicker {
        font-size: 0.66rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: #6a8a6a;
        margin-bottom: 0.35rem;
    }
    .siq-screening-notes ul {
        margin: 0;
        padding-left: 1.05rem;
    }
    .siq-screening-notes li { margin-bottom: 0.15rem; }
    .siq-screening-notes li:last-child { margin-bottom: 0; }

    /* ── Buttons ── */
    div[data-testid="stButton"] > button {
        font-family: 'Inter', sans-serif !important;
        font-weight: 700 !important; letter-spacing: -0.01em;
        border-radius: 9px !important;
    }
    div[data-testid="stButton"] > button[kind="primary"] {
        background: linear-gradient(135deg, #1d9e52, #145f34) !important;
        border: none !important; color: #fff !important;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #27ae60, #1d9e52) !important;
        box-shadow: 0 0 20px rgba(29,158,82,0.3) !important;
    }

    /* ── Tabs ── */
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        color: #1d9e52 !important; border-bottom-color: #1d9e52 !important; font-weight: 800 !important;
    }
    div[data-testid="stTabs"] button[role="tab"] { font-weight: 600 !important; color: #3a5a3a !important; }

    /* ── Inputs ── */
    div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea {
        font-family: 'Inter', sans-serif !important;
        border-radius: 8px !important;
    }

    /* ── Alert boxes — saturate + darken for readability ── */
    div[data-testid="stAlert"] {
        border-radius: 10px !important;
        font-weight: 600 !important;
        filter: saturate(2.2) brightness(0.82) !important;
    }
    div[data-testid="stAlert"] p,
    div[data-testid="stAlert"] strong,
    div[data-testid="stAlert"] a {
        font-weight: 600 !important;
        font-size: 0.92rem !important;
    }

    /* ── Expander ── */
    div[data-testid="stExpander"] {
        border: 1px solid #e2ede2 !important; border-radius: 10px !important;
    }

    .topo-feature-card {
        background: #ffffff;
        border: 1.5px solid #dce8f5;
        border-radius: 12px;
        padding: 1.1rem 1.15rem;
        margin-bottom: 0.75rem;
        box-shadow: 0 1px 4px rgba(21, 101, 192, 0.06);
        min-height: 0;
    }
    .topo-feature-title {
        font-size: 1.02rem;
        font-weight: 800;
        letter-spacing: -0.01em;
        color: #0d1a0d;
        line-height: 1.25;
    }
    .topo-feature-desc {
        font-size: 0.84rem;
        color: #4a6a8a;
        font-weight: 500;
        margin-top: 0.35rem;
        line-height: 1.55;
    }


</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="pvmath-header">
  <div class="pvmath-logo-mark">
    <i class="fa-solid fa-solar-panel" style="color:#fff;font-size:1.1rem;"></i>
  </div>
  <div>
    <div style="display:flex;align-items:baseline;gap:0.5rem;">
      <span class="pvmath-app-name">SiteIQ</span>
      <span class="pvmath-app-sub">by PVMath</span>
    </div>
    <div class="pvmath-tagline">Solar Site Intelligence Platform — fast pre-screening for utility-scale projects</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ─── Helper Functions ─────────────────────────────────────────────────────────

def geocode_address(address):
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1},
            headers={"User-Agent": "SiteIQ/1.0 (pvmath.com; contact@pvmath.com)"},
            timeout=10
        )
        data = r.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"]), data[0]["display_name"]
    except Exception:
        pass
    return None, None, None


def parse_google_maps_url(url):
    url = url.strip()
    plain = re.match(r'^(-?\d{1,3}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)$', url)
    if plain:
        return float(plain.group(1)), float(plain.group(2))
    for pattern in [
        r'@(-?\d+\.?\d+),(-?\d+\.?\d+)',
        r'q=(-?\d+\.?\d+),(-?\d+\.?\d+)',
        r'll=(-?\d+\.?\d+),(-?\d+\.?\d+)',
        r'place/[^/]+/@(-?\d+\.?\d+),(-?\d+\.?\d+)',
    ]:
        match = re.search(pattern, url)
        if match:
            return float(match.group(1)), float(match.group(2))
    return None, None


def polygon_area_ha(coords):
    if len(coords) < 3:
        return 0.0
    mean_lat = sum(c[0] for c in coords) / len(coords)
    lat_m  = 111320.0
    lon_m  = 111320.0 * math.cos(math.radians(mean_lat))
    pts = [(c[1] * lon_m, c[0] * lat_m) for c in coords]
    n = len(pts)
    area = abs(sum(pts[i][0] * pts[(i+1) % n][1] -
                   pts[(i+1) % n][0] * pts[i][1] for i in range(n))) / 2.0
    return round(area / 10000, 2)


def parse_kml_bytes(data: bytes):
    try:
        root = ET.fromstring(data)
        coords_el = root.find('.//{http://www.opengis.net/kml/2.2}coordinates')
        if coords_el is None:
            coords_el = root.find('.//coordinates')
        if coords_el is None:
            return None, None, None
        coords = []
        for token in coords_el.text.strip().split():
            parts = token.split(',')
            if len(parts) >= 2:
                coords.append((float(parts[1]), float(parts[0])))
        if not coords:
            return None, None, None
        clat = sum(c[0] for c in coords) / len(coords)
        clon = sum(c[1] for c in coords) / len(coords)
        area = polygon_area_ha(coords)
        return clat, clon, area
    except Exception:
        return None, None, None


def parse_kmz_bytes(data: bytes):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            kml_name = next((n for n in z.namelist() if n.endswith('.kml')), None)
            if kml_name:
                return parse_kml_bytes(z.read(kml_name))
    except Exception:
        pass
    return None, None, None


def get_flood_risk(lat, lon, elevation):
    """Elevation-based flood screening — not authoritative flood-zone data."""
    in_de = 47.3 <= lat <= 55.1 and  5.9 <= lon <= 15.1
    in_at = 46.4 <= lat <= 49.0 and  9.5 <= lon <= 17.2
    in_ch = 45.8 <= lat <= 47.8 and  5.9 <= lon <= 10.5

    if in_de:
        portal = "https://www.hochwasserportal.de"
        portal_name = "Hochwasserportal Deutschland"
    elif in_at:
        portal = "https://www.hora.gv.at"
        portal_name = "HORA — Hochwasserrisikozonierung Austria"
    elif in_ch:
        portal = "https://map.geo.admin.ch/?layers=ch.bafu.hydrologische-daten_pegel"
        portal_name = "Geo Admin — Schweiz Hochwasser"
    else:
        portal = "https://www.globalfloodmonitor.org"
        portal_name = "Global Flood Monitor"

    source = "OpenTopoData DEM (EU-DEM 25 m / SRTM 30 m) — centre elevation at screening coordinates"
    confidence = "Low — rule-based elevation heuristic; not official flood-zone mapping"

    if elevation is None:
        reason = "Elevation unavailable at screening coordinates"
        risk = "⚠️ Unknown"
        detail = (
            f"{reason}. Manual check required at {portal_name}. "
            f"Data source: {source}. Confidence: {confidence}."
        )
    elif elevation < 10:
        reason = f"Centre elevation {elevation} m asl is below 10 m — commonly associated with coastal/plain flood exposure"
        risk = "🔴 High Risk"
        detail = (
            f"{reason}. Verify HQ100 / official flood zones at {portal_name}. "
            f"Source: {source}. Confidence: {confidence}."
        )
    elif elevation < 50:
        reason = f"Centre elevation {elevation} m asl is below 50 m — low-lying terrain; proximity to watercourses not assessed"
        risk = "🟠 Moderate Risk"
        detail = (
            f"{reason}. Cross-check official flood maps at {portal_name}. "
            f"Source: {source}. Confidence: {confidence}."
        )
    elif elevation < 200:
        reason = f"Centre elevation {elevation} m asl is moderate — local drainage and watercourse proximity not screened"
        risk = "🟡 Low-Moderate Risk"
        detail = (
            f"{reason}. Verify at {portal_name} before commitment. "
            f"Source: {source}. Confidence: {confidence}."
        )
    else:
        reason = f"Centre elevation {elevation} m asl is relatively elevated — flood exposure likely lower at this pin"
        risk = "🟢 Low Risk"
        detail = (
            f"{reason}. Still verify at {portal_name} for bankable due diligence. "
            f"Source: {source}. Confidence: {confidence}."
        )

    return {
        "risk": risk,
        "detail": detail,
        "reason": reason,
        "source": source,
        "confidence": confidence,
        "portal": portal,
        "portal_name": portal_name,
    }


def _boundary_center(polygons):
    """BBox centre of enabled boundary rings — matches TopoIQ report coordinates."""
    if not polygons:
        return None, None
    all_lats = [p[0] for poly in polygons for p in poly]
    all_lons = [p[1] for poly in polygons for p in poly]
    return (min(all_lats) + max(all_lats)) / 2, (min(all_lons) + max(all_lons)) / 2


def _us_grid_operator(lat, lon):
    """Rough US ISO/RTO from coordinates — ERCOT called out for Texas sites."""
    if 25.8 <= lat <= 36.5 and -106.6 <= lon <= -93.5:
        return (
            "ERCOT",
            "Interconnection via ERCOT — submit LGIA with your transmission owner; "
            "queue position is often the critical-path timeline at utility scale",
        )
    if 36.0 <= lat <= 49.0 and -125.0 <= lon <= -66.0:
        if lon >= -104.0:
            return (
                "PJM / MISO / SPP",
                "Contact the applicable RTO (PJM, MISO, or SPP) and local transmission owner for queue entry",
            )
        return (
            "WECC / CAISO",
            "Contact WECC or CAISO and the local utility for large-generator interconnection",
        )
    return (
        "Regional ISO/RTO",
        "Contact local utility and applicable ISO/RTO for interconnection requirements",
    )


def _incentive_row_label(project_country, country):
    c = (project_country or country or "").lower()
    if any(x in c for x in ["usa", "united states", "america", "us"]):
        return "Federal Incentive (US)"
    if any(x in c for x in ["germany", "deutschland", "de"]):
        return "EEG / Incentive"
    return "Incentive / Tariff"


def _point_in_polygon(plat, plon, poly):
    """Ray-casting point-in-polygon test. poly = [[lat, lon], ...]."""
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        lat_i, lon_i = poly[i]
        lat_j, lon_j = poly[j]
        if (lon_i > plon) != (lon_j > plon):
            x = (lat_j - lat_i) * (plon - lon_i) / ((lon_j - lon_i) or 1e-15) + lat_i
            if plat < x:
                inside = not inside
        j = i
    return inside


def _haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _boundaries_from_project(proj):
    """Enabled site boundaries from Project Setup (coords as lon, lat)."""
    if proj.get("polygon_boundaries"):
        loaded = filter_boundary_list(list(proj["polygon_boundaries"]), latlon=True)
        return [
            {
                "id": b.get("id", f"proj_{i}"),
                "name": b.get("name", f"Boundary {i + 1}"),
                "coords": [(c[1], c[0]) for c in b["coords"]],
                "enabled": b.get("enabled", True),
            }
            for i, b in enumerate(loaded)
            if b.get("coords")
        ]
    pc = proj.get("polygon_coords")
    if proj.get("mode") == "full" and pc:
        return [{
            "id": "proj_0",
            "name": "Project boundary",
            "coords": [(c[1], c[0]) for c in pc],
            "enabled": True,
        }]
    return []


def _enabled_polygons_latlon(boundaries):
    """Convert enabled boundary rings to [[lat, lon], ...] for folium / terrain."""
    out = []
    for b in boundaries:
        if b.get("enabled") and b.get("coords"):
            out.append([(c[1], c[0]) for c in b["coords"]])
    return out


def get_terrain_data(lat, lon, polygon=None, polygons=None, radius_km=0.5):
    """
    Slope/elevation screening.
    - If `polygon` or `polygons` (site boundary rings as [[lat,lon],...]) is supplied,
      samples a grid of points across the ACTUAL boundary — same spirit as TopoIQ's
      just coarser — so the verdict reflects the whole site, not just the pin.
    - Otherwise (Quick Mode, pin only), samples a denser 8-direction ring around the pin
      (9 points total, up from the old 4-direction/5-point cross) for the best estimate
      obtainable from a single point.
    """
    in_europe = 34 <= lat <= 72 and -25 <= lon <= 45
    dataset   = "eudem25m" if in_europe else "srtm30m"

    poly_list = []
    if polygons:
        poly_list = [p for p in polygons if p and len(p) >= 3]
    elif polygon and len(polygon) >= 3:
        poly_list = [polygon]

    if poly_list:
        all_lats = [p[0] for poly in poly_list for p in poly]
        all_lons = [p[1] for poly in poly_list for p in poly]
        lat_min, lat_max = min(all_lats), max(all_lats)
        lon_min, lon_max = min(all_lons), max(all_lons)

        GRID_N = 7
        grid_pts = []
        for i in range(GRID_N):
            for j in range(GRID_N):
                glat = lat_min + (lat_max - lat_min) * (i + 0.5) / GRID_N
                glon = lon_min + (lon_max - lon_min) * (j + 0.5) / GRID_N
                if any(_point_in_polygon(glat, glon, poly) for poly in poly_list):
                    grid_pts.append((glat, glon))

        if len(grid_pts) < 4:
            clat, clon = sum(all_lats) / len(all_lats), sum(all_lons) / len(all_lons)
            grid_pts = [(clat, clon)]
            for poly in poly_list:
                grid_pts.extend(poly[:1])

        grid_pts = grid_pts[:40]  # keep the API request size reasonable
        locations = "|".join(f"{p[0]},{p[1]}" for p in grid_pts)
        try:
            r = requests.get(
                f"https://api.opentopodata.org/v1/{dataset}",
                params={"locations": locations}, timeout=20
            )
            results = r.json().get("results", [])
            pts = [(grid_pts[i][0], grid_pts[i][1], res["elevation"])
                   for i, res in enumerate(results) if res.get("elevation") is not None]
            if len(pts) < 4:
                return {"success": False, "error": "Insufficient data"}

            slopes = []
            for i, (la1, lo1, z1) in enumerate(pts):
                nearest = sorted(
                    ((j, _haversine_m(la1, lo1, pts[j][0], pts[j][1])) for j in range(len(pts)) if j != i),
                    key=lambda x: x[1]
                )[:3]
                for j, d in nearest:
                    if d > 0:
                        slopes.append(abs(pts[j][2] - z1) / d * 100)

            if not slopes:
                return {"success": False, "error": "Insufficient data"}

            zs = [p[2] for p in pts]
            return {
                "success":          True,
                "center_elev":      round(zs[len(zs) // 2], 1),
                "max_slope_pct":    round(max(slopes), 1),
                "elevation_range":  round(max(zs) - min(zs), 1),
                "sample_points":    len(pts),
                "pct_over5":        round(100 * sum(1 for s in slopes if s > 5) / len(slopes)),
                "pct_over10":       round(100 * sum(1 for s in slopes if s > 10) / len(slopes)),
                "boundary_sampled": True,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Quick Mode: denser 8-direction ring around the pin ────────────────────
    delta  = radius_km / 111.0
    dist_m = radius_km * 1000.0
    dirs = [
        (1, 0), (-1, 0), (0, 1), (0, -1),
        (0.7071, 0.7071), (0.7071, -0.7071), (-0.7071, 0.7071), (-0.7071, -0.7071),
    ]
    points = [(lat, lon)] + [(lat + dy * delta, lon + dx * delta) for dy, dx in dirs]
    locations = "|".join(f"{p[0]},{p[1]}" for p in points)
    try:
        r = requests.get(
            f"https://api.opentopodata.org/v1/{dataset}",
            params={"locations": locations},
            timeout=15
        )
        results = r.json().get("results", [])
        elevs = [res["elevation"] for res in results if res.get("elevation") is not None]
        if len(elevs) >= 5:
            center = elevs[0]
            slopes = [abs(e - center) / dist_m * 100 for e in elevs[1:]]
            return {
                "success":          True,
                "center_elev":      round(center, 1),
                "max_slope_pct":    round(max(slopes), 1),
                "elevation_range":  round(max(elevs) - min(elevs), 1),
                "sample_points":    len(elevs),
                "boundary_sampled": False,
            }
    except Exception as e:
        return {"success": False, "error": str(e)}
    return {"success": False, "error": "Insufficient data"}


def assess_slope(pct, mount_type="Fixed Tilt", sparse_screening=False, sample_points=0):
    if mount_type == "Single-Axis Tracker":
        if pct <= 3:
            lbl, color, detail = "✅ Excellent", "green", f"{pct}% — Ideal for single-axis tracker"
        elif pct <= 6:
            lbl, color, detail = "⚠️ Acceptable", "yellow", f"{pct}% — Feasible for tracker; grading may be needed"
        elif pct <= 10:
            lbl, color, detail = "⚠️ Challenging", "yellow", f"{pct}% — Steep for trackers; significant grading required"
        else:
            lbl, color, detail = "❌ Critical", "red", f"{pct}% — Too steep for single-axis tracker systems"
    else:
        if pct <= 5:
            lbl, color, detail = "✅ Excellent", "green", f"{pct}% — Ideal for fixed-tilt ground mount"
        elif pct <= 10:
            lbl, color, detail = "⚠️ Acceptable", "yellow", f"{pct}% — Feasible; some earthworks expected"
        elif pct <= 15:
            lbl, color, detail = "⚠️ Challenging", "yellow", f"{pct}% — Significant earthworks required"
        else:
            lbl, color, detail = "❌ Critical", "red", f"{pct}% — Too steep; likely not viable"

    if sparse_screening:
        n = sample_points or "few"
        q_word = lbl.replace("✅ ", "").replace("⚠️ ", "").replace("❌ ", "").split("—")[0].strip()
        if q_word in ("Excellent", "Good"):
            lbl = f"✅ {q_word} (Indicative)"
            color = "green"
        elif q_word in ("Acceptable",):
            lbl = f"⚠️ {q_word} (Indicative)"
            color = "yellow"
        else:
            lbl = f"⚠️ {q_word} (Indicative)"
        detail = (
            f"Sparse sample: {pct}% max ({n} OpenTopoData points) — {q_word.lower()} "
            f"indicators in the sample; confirm site-wide terrain in TopoIQ before bankable use."
        )
    return lbl, color, detail


def assess_solar(ghi):
    if ghi >= 1300:
        return "✅ Excellent", "green",  f"{ghi} kWh/m²/yr — Premium solar resource"
    elif ghi >= 1100:
        return "✅ Good",      "green",  f"{ghi} kWh/m²/yr — Good resource for DACH"
    elif ghi >= 900:
        return "⚠️ Moderate",  "yellow", f"{ghi} kWh/m²/yr — Viable but below DACH average"
    else:
        return "❌ Poor",      "red",    f"{ghi} kWh/m²/yr — Low resource; financial risk"


def assess_eeg(lat, lon, land_use="Standard", project_country=""):
    c = project_country.lower().strip()
    agri = land_use == "Agri-PV"

    in_de = any(x in c for x in ["germany","deutschland","german"]) or \
            (not c and 47.3 <= lat <= 55.1 and 5.9 <= lon <= 15.1)
    in_at = any(x in c for x in ["austria","österreich","oesterreich"]) or \
            (not c and 46.4 <= lat <= 49.0 and 9.5 <= lon <= 17.2)
    in_ch = any(x in c for x in ["switzerland","schweiz","suisse","svizzera"]) or \
            (not c and 45.8 <= lat <= 47.8 and 5.9 <= lon <= 10.5)
    in_it = any(x in c for x in ["italy","italia","italie"])
    in_es = any(x in c for x in ["spain","españa","espana","spanish"])
    in_fr = any(x in c for x in ["france","frankreich","frankrijk","french"])
    in_pl = any(x in c for x in ["poland","polska"])
    in_nl = any(x in c for x in ["netherlands","nederland","holland"])
    in_us = any(x in c for x in ["usa","united states","america","us"])
    in_in = any(x in c for x in ["india","bharat","indian"])
    in_au = any(x in c for x in ["australia","australian","oz"])
    in_uk = any(x in c for x in ["uk","united kingdom","england","britain"])
    in_jp = any(x in c for x in ["japan","japanese"])
    in_br = any(x in c for x in ["brazil","brasil","brazilian"])
    in_za = any(x in c for x in ["south africa","southafrica"])

    if in_de:
        if agri:
            return "Germany", "EEG 2023 Agri-PV bonus eligible", "Register at Bundesnetzagentur — DIN SPEC 91434 compliance required"
        return "Germany", "EEG 2023 standard Freifläche tariff", "Register at Bundesnetzagentur (Marktstammdatenregister)"
    elif in_at:
        if agri:
            return "Austria", "Agri-PV eligible under EAG", "OeMAG feed-in tariff — contact Energie-Control Austria"
        return "Austria", "EAG feed-in tariff applicable", "OeMAG registration — Energie-Control Austria"
    elif in_ch:
        return "Switzerland", "KEV / Einmalvergütung (EVS) applicable", "Register via Pronovo — Swiss Energy Act (EnG)"
    elif in_it:
        if agri:
            return "Italy", "Agri-PV eligible under FER Decreto", "GSE registration — dual-use agricultural permit required at Comune"
        return "Italy", "FER Decreto / incentive applicable", "GSE (Gestore dei Servizi Energetici) registration required"
    elif in_es:
        return "Spain", "RESA auction / OMIE market access", "No fixed FIT — competitive auction via CNMC / REE"
    elif in_fr:
        if agri:
            return "France", "Agri-PV CRE auction applicable", "CRE appel d'offres — dual-use zone agricole permit required"
        return "France", "CRE auction applicable (> 500 kWp)", "CRE (Commission de Regulation de l'Energie) registration"
    elif in_pl:
        return "Poland", "RES auction system (URE)", "Competitive bidding — Urzad Regulacji Energetyki (URE)"
    elif in_nl:
        return "Netherlands", "SDE++ subsidy applicable", "RVO registration — grid congestion check critical (Liander/Stedin/Enexis)"
    elif in_us:
        iso, iso_note = _us_grid_operator(lat, lon)
        return "United States", "ITC 30% + IRA bonus credits applicable", f"{iso} — {iso_note}"
    elif in_in:
        if agri:
            return "India", "PM-KUSUM / MNRE Agri-PV scheme applicable", "SECI or state DISCOM tender — contact MNRE for Agri-PV guidelines"
        return "India", "MNRE / SECI auction or state DISCOM PPA", "CERC framework — contact state DISCOM for grid connectivity"
    elif in_au:
        return "Australia", "LGC (Large-scale Generation Certificates) — RET scheme", "AEMO registration — check state-level planning rules"
    elif in_uk:
        return "United Kingdom", "CfD (Contracts for Difference) auction applicable", "Ofgem / National Grid ESO — grid connection offer required"
    elif in_jp:
        return "Japan", "FIT / FIP (Feed-in Premium) scheme applicable", "METI registration — contact local power utility (TEPCO, Kansai etc.)"
    elif in_br:
        return "Brazil", "ANEEL auction / net metering (GD) applicable", "ANEEL registration — contact local DISCOM (CEMIG, COPEL, CPFL etc.)"
    elif in_za:
        return "South Africa", "REIPPPP auction or wheeling agreement", "NERSA registration — contact Eskom or municipality DSO"
    else:
        name = project_country.title() if project_country else "Location"
        return name, "Check local renewable energy incentive scheme", "Contact national energy regulatory authority for grid connection"


def _fmt_metric_num(val, decimals=1):
    if val is None or val == "—":
        return "—"
    try:
        v = float(val)
        if decimals == 0:
            return f"{v:,.0f}"
        s = f"{v:,.{decimals}f}"
        return s.rstrip("0").rstrip(".") if decimals > 0 else s
    except (TypeError, ValueError):
        return str(val)


def _metric_card_html(icon, color, label, number, unit):
    return (
        f'<div class="metric-card">'
        f'<div class="mc-icon"><i class="fa-solid {icon}" style="color:{color};"></i></div>'
        f'<div class="mc-label">{label}</div>'
        f'<div class="mc-value-row">'
        f'<span class="mc-number">{number}</span>'
        f'<span class="mc-unit">{unit}</span>'
        f'</div></div>'
    )


def _slope_quality_tier(pct, mount_type="Fixed Tilt") -> int:
    """Tier from slope % alone — used when boundary sparse sample has favorable readings."""
    if pct is None:
        return 1
    if mount_type == "Single-Axis Tracker":
        if pct <= 3:
            return 5
        if pct <= 6:
            return 3
        if pct <= 10:
            return 2
        return 0
    if pct <= 5:
        return 5
    if pct <= 10:
        return 3
    if pct <= 15:
        return 2
    return 0


def _param_tier(lbl: str) -> int:
    """Higher = better. 0 = critical / failed."""
    if "❌" in lbl:
        return 0
    if "Data unavailable" in lbl:
        return 1
    if "(Indicative)" in lbl or "Indicative only" in lbl:
        if "Excellent" in lbl:
            return 5
        if "Good" in lbl:
            return 4
        if "Acceptable" in lbl or "Moderate" in lbl:
            return 3
        if "Challenging" in lbl:
            return 2
        if "Critical" in lbl or "Poor" in lbl:
            return 0
        return 3
    if "Challenging" in lbl:
        return 2
    if "Acceptable" in lbl or "Moderate" in lbl:
        return 3
    if "Good" in lbl:
        return 4
    if "Excellent" in lbl:
        return 5
    return 3


def _sparse_topo_note(sample_points: int = 0) -> str:
    n = sample_points or "sparse"
    return (
        f" Terrain from an OpenTopoData boundary sample ({n} points) — "
        f"favorable sample indicators; run TopoIQ to confirm before bankable use."
    )


def overall_verdict(
    slope_lbl,
    solar_lbl,
    land_use="Standard",
    mount_type="Fixed Tilt",
    slope_pct=None,
    sparse_screening=False,
    sample_points=0,
):
    sparse = sparse_screening or "(Indicative)" in slope_lbl or "Indicative only" in slope_lbl
    if sparse and slope_pct is not None:
        slope_tier = _slope_quality_tier(slope_pct, mount_type)
    else:
        slope_tier = _param_tier(slope_lbl)
    solar_tier = _param_tier(solar_lbl)
    tiers = [slope_tier, solar_tier]
    worst = min(tiers)
    best = max(tiers)
    if land_use == "Agri-PV":
        label = f"Agri-PV {mount_type}"
    else:
        label = mount_type

    if worst == 0:
        return "❌ CRITICAL", (
            "One or more parameters exceed viability threshold. "
            "High risk — reconsider site or system type."
        )
    if worst == 1:
        return "⚠️ CHALLENGING", (
            "Missing solar or terrain data — detailed study mandatory "
            "before treating this screening as bankable."
        )
    if worst == 2 and sparse and slope_tier <= 2:
        return "⚠️ CHALLENGING", (
            "Sparse terrain sample indicates steep or near-limit slopes — "
            "detailed civil study mandatory; run TopoIQ for confirmed metrics."
        )
    if worst == 2:
        return "⚠️ CHALLENGING", (
            "One or more parameters are near the viability limit. "
            "Detailed civil and energy study mandatory before commitment."
        )
    if worst == 5:
        verdict = "✅ EXCELLENT"
        txt = (
            f"Strong {label} potential. All parameters in ideal range — "
            f"proceed to detailed feasibility study."
        )
        if sparse:
            verdict = "✅ VERY GOOD"
            txt += _sparse_topo_note(sample_points)
        return verdict, txt
    if worst == 4 and best == 5:
        txt = (
            f"Strong {label} site — key parameters are good to excellent. "
            f"Proceed to detailed feasibility study."
        )
        if sparse:
            txt += _sparse_topo_note(sample_points)
        return "✅ VERY GOOD", txt
    if worst == 4:
        txt = (
            f"Strong {label} potential. Key parameters are in the good range — "
            f"proceed to detailed feasibility study."
        )
        if sparse:
            txt += _sparse_topo_note(sample_points)
        return "✅ GOOD", txt
    if worst == 3 and best >= 4:
        txt = (
            f"Strong {label} site with one noted constraint. "
            f"Proceed to detailed feasibility — address the moderate factor in design."
        )
        if sparse:
            txt += _sparse_topo_note(sample_points)
        return "✅ GOOD", txt
    txt = (
        f"Site is viable with noted considerations. "
        f"Address constraints in detailed {label} design."
    )
    if sparse:
        txt += _sparse_topo_note(sample_points)
    return "⚠️ ACCEPTABLE", txt


def get_next_steps(project_country, land_use="Standard", lat=None, lon=None):
    c = project_country.lower().strip()
    agri = land_use == "Agri-PV"

    if any(x in c for x in ["germany", "deutschland", "de"]):
        steps = [
            "Verify land classification (Nutzungsart) with local Katasteramt",
            "Grid connection: contact local DSO (e.g. Bayernwerk, E.ON, Netze BW)",
            "Planning permission: consult local Bauamt / Gemeindeverwaltung",
            "EEG 2023 feed-in tariff: register via Bundesnetzagentur (Marktstammdatenregister)",
            "Flood risk: www.hochwasserportal.de — verify HQ100 flood zone",
        ]
        if agri:
            steps.append("Agronomic study required for DIN SPEC 91434 Agri-PV compliance")
    elif any(x in c for x in ["austria", "österreich", "oesterreich"]):
        steps = [
            "Land use: check Flächenwidmungsplan with local Gemeinde",
            "Grid connection: contact local DSO (e.g. Wien Energie, Netz Niederösterreich)",
            "Incentives: OeMAG feed-in tariff under EAG (Erneuerbaren-Ausbau-Gesetz)",
            "Planning: Baubehörde approval required — check cantonal / Landesrecht",
            "Flood risk: www.hora.gv.at — check HW100 flood zones",
        ]
    elif any(x in c for x in ["switzerland", "schweiz", "suisse", "svizzera"]):
        steps = [
            "Land use: verify Nutzungszone with local Gemeinde / Kanton",
            "Grid connection: contact local DSO (e.g. BKW, EKZ, Romande Énergie)",
            "Incentives: Pronovo KEV / Einmalvergütung (EVS) registration",
            "Planning: Baubewilligung from Gemeinde — Raumplanungsgesetz applies",
            "Flood risk: map.geo.admin.ch — check Hochwassergefahrenkarte",
        ]
    elif any(x in c for x in ["italy", "italia", "italie"]):
        steps = [
            "Grid connection: contact local DSO (Enel Distribuzione, A2A, ACEA)",
            "Planning permission: Comune / Regione — check Piano Regolatore Generale (PRG)",
            "Incentives: GSE (Gestore dei Servizi Energetici) — Conto Energia / FER Decreto",
            "Environmental impact: VIA procedure required for projects > 1 MWp",
            "Land use: verify zoning classification at local Comune / Regione" if not agri else
            "Land use: verify zona agricola E classification — Agri-PV requires dual-use permit at Comune",
        ]
    elif any(x in c for x in ["spain", "españa", "espana"]):
        steps = [
            "Grid connection: contact REE or local DSO (Endesa, Iberdrola, Naturgy)",
            "Planning: Ayuntamiento licence + Comunidad Autonoma environmental permit",
            "Incentives: OMIE market access — no fixed FIT, competitive auctions (RESA scheme)",
            "Environmental: EIA (Evaluacion de Impacto Ambiental) for projects > 50 MWp",
            "Land use: verify suelo rustico / no urbanizable classification at Ayuntamiento" if not agri else
            "Land use: Agri-PV — verify suelo agricola classification + dual-use planning consent",
        ]
    elif any(x in c for x in ["france", "frankreich", "frankrijk"]):
        steps = [
            "Grid connection: contact Enedis or local DSO — TURPE tariff applies",
            "Planning: Permis de construire from Mairie — check PLU (Plan Local d'Urbanisme)",
            "Incentives: CRE auction (Appel d'Offres) for projects > 500 kWp",
            "Environmental: Etude d'impact required for large-scale projects",
            "Land use: verify zoning classification in PLU with local Mairie" if not agri else
            "Land use: Agri-PV — verify zone agricole (A) in PLU — dual-use decree applies",
        ]
    elif any(x in c for x in ["poland", "polska"]):
        steps = [
            "Grid connection: contact local DSO (Tauron, Energa, Enea, PGE)",
            "Planning: local spatial development plan (MPZP) — check with Gmina",
            "Incentives: RES auctions (URE) — competitive bidding system",
            "Environmental: EIA required for projects > 1 MWp",
            "Land use: verify zoning classification with local Gmina" if not agri else
            "Land use: agricultural land class I-III requires special permit for Agri-PV in Poland",
        ]
    elif any(x in c for x in ["netherlands", "nederland", "holland"]):
        steps = [
            "Grid connection: contact Liander, Stedin, or Enexis — grid congestion check critical",
            "Planning: Omgevingsvergunning from Gemeente — check bestemmingsplan",
            "Incentives: SDE++ subsidy (Stimulering Duurzame Energieproductie) via RVO",
            "Environmental: MER (milieueffectrapportage) for large projects",
            "Land use: verify bestemming in bestemmingsplan — provincial approval may be needed" if not agri else
            "Land use: Agri-PV — verify agrarisch bestemming — provincial approval required",
        ]
    elif any(x in c for x in ["usa", "united states", "america"]):
        iso, _ = _us_grid_operator(lat, lon) if lat is not None and lon is not None else ("your regional ISO/RTO", "")
        steps = [
            f"Interconnection: submit LGIA / queue application with your transmission owner in {iso} — at utility scale this is often the critical-path timeline",
            "Environmental: wetlands (USACE), threatened species (USFWS), and cultural-resource screening — frequently the long-pole item on large sites",
            "Planning: county zoning permit + conditional use permit (CUP)",
            "Incentives: ITC (Investment Tax Credit) 30% + IRA bonus credits",
            "Land use: verify zoning classification with county assessor" if not agri else
            "Land use: Agri-PV — verify agricultural zoning and dual-use approval with county",
        ]
    elif any(x in c for x in ["india", "bharat"]):
        steps = [
            "Grid connection: DISCOM connectivity — ISTS or SISTS depending on scale",
            "Incentives: MNRE tender / SECI auction or state DISCOM PPA",
            "Planning: state-level approval — check with relevant DISCOM / SLDC",
            "Land use: land acquisition / lease from state government or private owner",
            "Environmental: EIA notification — Category A/B project classification",
        ]
    elif any(x in c for x in ["australia", "oz"]):
        steps = [
            "Grid connection: AEMO registration — check network access rules per state",
            "Planning: development application (DA) to local council",
            "Incentives: LGC (Large-scale Generation Certificates) under RET scheme",
            "Environmental: state-level EIA / EIS process",
            "Land use: verify zoning classification — rural or primary production zone" if not agri else
            "Land use: Agri-PV — verify primary production zone + dual-use planning with council",
        ]
    else:
        steps = [
            f"Grid connection: contact the national grid operator / local DSO in {project_country}",
            f"Planning permission: local municipality / regional planning authority in {project_country}",
            "Environmental impact assessment: check national threshold requirements for solar",
            "Feed-in tariff / incentive scheme: contact national energy regulatory authority",
            "Land use: verify zoning and land classification with local authority",
        ]
        if agri:
            steps.append("Agri-PV dual-use: verify national / regional agricultural dual-use regulations")

    return [f"{i+1}. {s}" for i, s in enumerate(steps)]


def _tier_to_score(tier: int, *, indicative: bool = False, topoiq: bool = False) -> int:
    base = {5: 95, 4: 88, 3: 75, 2: 55, 1: 50, 0: 30}.get(tier, 70)
    if topoiq and tier >= 4:
        return min(98, base + 2)
    if indicative and tier >= 4:
        return max(50, base - 5)
    return base


def _ghi_to_score(ghi) -> int:
    try:
        g = float(ghi)
    except (TypeError, ValueError):
        return 50
    if g >= 2200:
        return 98
    if g >= 2000:
        return 95
    if g >= 1800:
        return 90
    if g >= 1600:
        return 85
    if g >= 1300:
        return 80
    if g >= 1100:
        return 70
    if g >= 900:
        return 55
    return 40


def _flood_risk_to_score(flood_risk: str) -> int:
    r = (flood_risk or "").upper()
    if "HIGH" in r and "LOW" not in r:
        return 40
    if "MODERATE" in r and "LOW" not in r:
        return 60
    if "LOW-MOD" in r or "LOW-MODERATE" in r:
        return 70
    if "LOW" in r:
        return 90
    return 50


def _land_use_to_score(land_use: str) -> int:
    return 85 if land_use == "Agri-PV" else 90


def _regulatory_to_score(country: str, eeg_status: str, project_country: str) -> int:
    c = (project_country or country or "").lower()
    status = (eeg_status or "").lower()
    _strong = (
        "germany", "deutschland", "united states", "usa", "america",
        "spain", "france", "italy", "australia", "india", "united kingdom",
    )
    if any(x in c for x in _strong) and status and "check local" not in status:
        return 85
    if status and any(w in status for w in ("applicable", "eligible", "auction", "itc", "eeg")):
        return 80
    return 70


def _verdict_label_from_score(score: int) -> str:
    return get_verdict_from_score(score)


SUITABILITY_WEIGHTS = (
    ("Solar Resource", "solar", 35),
    ("Terrain", "terrain", 25),
    ("Flood Risk", "flood", 15),
    ("Land Use", "land", 15),
    ("Grid / Regulatory", "regulatory", 10),
)


def compute_site_suitability(
    solar_lbl,
    slope_lbl,
    flood_risk,
    land_use,
    solar,
    terrain,
    mount_type="Fixed Tilt",
    country="",
    eeg_status="",
    project_country="",
    cap=None,
) -> dict:
    """Weighted suitability breakdown + key drivers for PDF."""
    solar_tier = _param_tier(solar_lbl)
    if terrain.get("topoiq_confirmed") and terrain.get("mean_slope_pct") is not None:
        slope_tier = _slope_quality_tier(terrain["mean_slope_pct"], mount_type)
        terrain_indicative = False
        terrain_topoiq = True
    elif "(Indicative)" in slope_lbl or terrain.get("boundary_sampled"):
        pct = terrain.get("mean_slope_pct") or terrain.get("max_slope_pct")
        slope_tier = _slope_quality_tier(pct, mount_type) if pct is not None else _param_tier(slope_lbl)
        terrain_indicative = True
        terrain_topoiq = False
    else:
        slope_tier = _param_tier(slope_lbl)
        terrain_indicative = False
        terrain_topoiq = False

    solar_score = _ghi_to_score(solar.get("annual_ghi") if solar.get("success") else None)
    if solar_tier < 4 and solar.get("success"):
        solar_score = min(solar_score, _tier_to_score(solar_tier))

    terrain_score = _tier_to_score(
        slope_tier, indicative=terrain_indicative, topoiq=terrain_topoiq,
    )
    flood_score = _flood_risk_to_score(flood_risk)
    land_score = _land_use_to_score(land_use)
    reg_score = _regulatory_to_score(country, eeg_status, project_country)

    raw = {
        "solar": solar_score,
        "terrain": terrain_score,
        "flood": flood_score,
        "land": land_score,
        "regulatory": reg_score,
    }
    overall = calculate_pvmath_score(raw)

    drivers = []
    if solar.get("success"):
        ghi = solar.get("annual_ghi")
        if ghi is not None and float(ghi) >= 1300:
            drivers.append(("positive", f"Excellent solar resource ({float(ghi):,.1f} kWh/m²/yr)"))
        elif ghi is not None:
            drivers.append(("positive", f"Solar resource {float(ghi):,.1f} kWh/m²/yr"))

    if terrain.get("success"):
        if terrain.get("topoiq_confirmed") and terrain.get("mean_slope_pct") is not None:
            drivers.append((
                "positive",
                f"Low terrain constraints (mean slope {terrain['mean_slope_pct']:.1f}%)",
            ))
        elif terrain.get("max_slope_pct") is not None and float(terrain["max_slope_pct"]) <= 6:
            drivers.append((
                "positive",
                f"Favourable sample slope ({terrain['max_slope_pct']:.1f}% max in screening sample)",
            ))

    if cap and cap.get("mwp_lo") is not None:
        drivers.append((
            "positive",
            f"Utility-scale development potential ({format_mwp_range(cap['mwp_lo'], cap['mwp_hi'])})",
        ))

    drivers.append(("warn", "Flood assessment based on screening-level data only"))
    if terrain.get("boundary_sampled") and not terrain.get("topoiq_confirmed"):
        drivers.append(("warn", "Terrain confirmation recommended via TopoIQ"))

    return {
        "scores": raw,
        "overall": overall,
        "verdict_label": get_verdict_from_score(overall),
        "drivers": drivers,
        "pvmath_score": overall,
    }


def compute_verdict_scores(
    solar_lbl,
    slope_lbl,
    flood_risk,
    land_use,
    solar,
    terrain,
    mount_type="Fixed Tilt",
) -> dict:
    s = compute_site_suitability(
        solar_lbl, slope_lbl, flood_risk, land_use, solar, terrain, mount_type,
    )
    return {
        "Irradiance": s["scores"]["solar"],
        "Terrain": s["scores"]["terrain"],
        "Flood": s["scores"]["flood"],
        "Land Use": s["scores"]["land"],
        "Overall": s["overall"],
    }

def build_pdf(site_name, lat, lon, area_ha, solar, terrain,
              country, eeg_status, eeg_note,
              slope_lbl, solar_lbl, verdict, verdict_txt,
              cap,
              land_use="Standard", mount_type="Fixed Tilt",
              project_country="", location_label="",
              flood_risk="", flood_detail="", flood_source="", flood_confidence="",
              flood_reason="", coord_note="",
              prepared_by="", module_confidence="",
              analysis_ref=None,
              pvmath_score=None, pvmath_verdict="", benchmark=None):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm,  bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    # ── Brand colours matching pvmath.com ─────────────────────────────────────
    GREEN    = colors.HexColor("#1d9e52")
    GREEN_DK = colors.HexColor("#145f34")
    ORANGE   = colors.HexColor("#e85d04")
    ORANGE_DK= colors.HexColor("#c24a00")
    LGRAY    = colors.HexColor("#f5f7f5")
    BORDER   = colors.HexColor("#d4e0d4")
    DARK_TXT = colors.HexColor("#1a2e1a")
    MUTED    = colors.HexColor("#5a7a5a")

    C_GREEN  = colors.HexColor("#1d9e52")
    C_LGREEN = colors.HexColor("#d1fae5")
    C_LGREEN2= colors.HexColor("#e8f5ee")
    C_YELLOW = colors.HexColor("#f59e0b")
    C_LYELLOW= colors.HexColor("#fef9c3")
    C_ORANGE = colors.HexColor("#ea580c")
    C_LORANG = colors.HexColor("#ffedd5")
    C_RED    = colors.HexColor("#dc2626")
    C_LRED   = colors.HexColor("#fee2e2")

    # ── Rainbow bar colours by month (N-hemisphere seasonal) ─────────────────
    _MONTH_COLORS = [
        "#f87171",  # Jan — winter red
        "#fb923c",  # Feb — orange
        "#facc15",  # Mar — yellow
        "#a3e635",  # Apr — light green
        "#4ade80",  # May — green
        "#22c55e",  # Jun — peak green
        "#22c55e",  # Jul — peak green
        "#4ade80",  # Aug — green
        "#a3e635",  # Sep — light green
        "#facc15",  # Oct — yellow
        "#fb923c",  # Nov — orange
        "#f87171",  # Dec — winter red
    ]

    def lp(text, color=DARK_TXT, bold=False, size=8.5):
        fn = "Helvetica-Bold" if bold else "Helvetica"
        return Paragraph(pdf_escape(str(text)), ParagraphStyle("lp", parent=styles["Normal"],
                         fontSize=size, fontName=fn, textColor=color,
                         leading=11, spaceAfter=0, wordWrap="LTR"))

    def section_hdr(text):
        """Section title with orange left-accent stripe."""
        t = Table([[
            Paragraph("", ParagraphStyle("x", parent=styles["Normal"])),
            Paragraph(text, ParagraphStyle("sh", parent=styles["Normal"],
                      fontSize=11, fontName="Helvetica-Bold",
                      textColor=DARK_TXT, leading=14)),
        ]], colWidths=[0.28*cm, 16.72*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (0,-1), ORANGE),
            ("TOPPADDING",    (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("LEFTPADDING",   (1,0), (1,-1), 8),
            ("RIGHTPADDING",  (0,0), (-1,-1), 0),
            ("LEFTPADDING",   (0,0), (0,-1), 0),
        ]))
        return t

    story = []

    # ── Orange header bar (matches website mockup) ────────────────────────────
    hdr = Table([[
        Paragraph("SITEIQ — SITE ASSESSMENT REPORT",
            ParagraphStyle("ht", parent=styles["Normal"], fontSize=14,
                           fontName="Helvetica-Bold", textColor=colors.white,
                           leading=17)),
        Paragraph("PVMath &nbsp;·&nbsp; pvmath.com",
            ParagraphStyle("hs", parent=styles["Normal"], fontSize=8.5,
                           textColor=colors.HexColor("#ffd0b5"), alignment=2,
                           leading=12)),
    ]], colWidths=["63%", "37%"])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), ORANGE),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0),(-1,-1), 13),
        ("BOTTOMPADDING", (0,0),(-1,-1), 13),
        ("LEFTPADDING",   (0,0),(-1,-1), 14),
        ("RIGHTPADDING",  (0,0),(-1,-1), 14),
    ]))
    story += [hdr, Spacer(1, 0.4*cm)]

    site_rows = [
        [lp("Project Name", bold=True), lp(site_name or "—")],
        [lp("Location", bold=True), lp(location_label or project_country or country or "—")],
        [lp("Country", bold=True), lp(project_country or country or "—")],
        [lp("Coordinates", bold=True),
         lp(f"{format_coords(lat, lon)}" + (f" ({coord_note})" if coord_note else ""))],
        [lp("Site Area", bold=True), lp(f"{area_ha} ha")],
        [lp("Land Use Type", bold=True), lp(land_use)],
        [lp("Mounting System", bold=True), lp(mount_type)],
        [lp("Report Date", bold=True), lp(datetime.now().strftime("%d.%m.%Y"))],
    ]
    if prepared_by:
        site_rows.append([lp("Prepared by", bold=True), lp(prepared_by)])
    if module_confidence:
        site_rows.append([lp("Module confidence", bold=True), lp(module_confidence)])
    t = Table(site_rows, colWidths=[5*cm, 12*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(0,-1), colors.HexColor("#e8f5e9")),
        ("VALIGN",       (0,0),(-1,-1), "TOP"),
        ("FONTSIZE",     (0,0),(-1,-1), 10),
        ("GRID",         (0,0),(-1,-1), 0.5, colors.lightgrey),
        ("TOPPADDING",   (0,0),(-1,-1), 6),
        ("BOTTOMPADDING",(0,0),(-1,-1), 6),
        ("LEFTPADDING",  (0,0),(-1,-1), 6),
        ("RIGHTPADDING", (0,0),(-1,-1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.5*cm))

    # ── Verdict styling (green/amber/red depending on result) ────────────────
    _is_positive = any(x in verdict for x in ("EXCELLENT", "VERY GOOD", "GOOD"))
    _is_acc  = "ACCEPTABLE" in verdict or "CHALLENGING" in verdict
    v_color  = C_GREEN if _is_positive else (C_YELLOW if _is_acc else C_RED)
    v_bg     = C_LGREEN if _is_positive else (C_LYELLOW if _is_acc else C_LRED)
    v_border = GREEN if _is_positive else (C_YELLOW if _is_acc else C_RED)

    story.append(Spacer(1, 0.1*cm))
    story.append(section_hdr("OVERALL VERDICT"))
    story.append(Spacer(1, 0.15*cm))
    _pdf_verdict = strip_pdf_label(verdict)
    vt = Table([[
        Paragraph(f"<b>{_pdf_verdict}</b>",
            ParagraphStyle("V", parent=styles["Normal"], fontSize=13,
                           fontName="Helvetica-Bold", textColor=v_color, leading=16)),
        Paragraph(verdict_txt,
            ParagraphStyle("Vt", parent=styles["Normal"], fontSize=9,
                           textColor=DARK_TXT, leading=13)),
    ]], colWidths=[6.5*cm, 10.5*cm])
    vt.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), v_bg),
        ("BACKGROUND",    (0,0),(0,-1),  v_bg),
        ("BOX",           (0,0),(-1,-1), 1.5, v_border),
        ("LEFTLINEWIDTH", (0,0),(0,-1),  4),
        ("TOPPADDING",    (0,0),(-1,-1), 11),
        ("BOTTOMPADDING", (0,0),(-1,-1), 11),
        ("LEFTPADDING",   (0,0),(-1,-1), 12),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]))
    story.append(vt)
    story.append(Spacer(1, 0.35*cm))

    _suit = compute_site_suitability(
        solar_lbl, slope_lbl, flood_risk, land_use, solar, terrain, mount_type,
        country=country, eeg_status=eeg_status, project_country=project_country, cap=cap,
    )
    story.append(section_hdr("SITE SUITABILITY BREAKDOWN"))
    story.append(Spacer(1, 0.12*cm))
    story.append(Paragraph(
        f"<b>Overall Score: {_suit['overall']}/100 "
        f"(<font color='#1d9e52'>{_suit['verdict_label']}</font>)</b>",
        ParagraphStyle("OvScore", parent=styles["Normal"], fontSize=11,
                       fontName="Helvetica-Bold", textColor=DARK_TXT, leading=15),
    ))
    story.append(Spacer(1, 0.15*cm))

    def _score_cell(val):
        return Paragraph(
            str(val),
            ParagraphStyle("sc", parent=styles["Normal"], fontSize=8,
                           textColor=DARK_TXT, alignment=2),
        )

    def _weight_cell(val):
        return Paragraph(
            f"{val}%",
            ParagraphStyle("wt", parent=styles["Normal"], fontSize=8,
                           textColor=MUTED, alignment=2),
        )

    _brk_rows = [
        [lp("Category", colors.white, bold=True, size=8),
         Paragraph("Score", ParagraphStyle("bh1", parent=styles["Normal"], fontSize=8,
                   fontName="Helvetica-Bold", textColor=colors.white, alignment=2)),
         Paragraph("Weight", ParagraphStyle("bh2", parent=styles["Normal"], fontSize=8,
                   fontName="Helvetica-Bold", textColor=colors.white, alignment=2))],
    ]
    for label, key, weight in SUITABILITY_WEIGHTS:
        _brk_rows.append([
            lp(label, DARK_TXT, size=8),
            _score_cell(_suit["scores"][key]),
            _weight_cell(weight),
        ])
    brk_t = Table(_brk_rows, colWidths=[8.5*cm, 4*cm, 4.5*cm])
    brk_t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), ORANGE),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.lightgrey),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("ALIGN",         (1,0), (-1,-1), "RIGHT"),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, LGRAY]),
    ]))
    story.append(brk_t)
    story.append(Spacer(1, 0.35*cm))

    story.append(section_hdr("KEY DRIVERS"))
    story.append(Spacer(1, 0.12*cm))
    for kind, text in _suit["drivers"]:
        if kind == "positive":
            icon, icol = "+", C_GREEN
        else:
            icon, icol = "!", C_ORANGE
        story.append(Paragraph(
            f'<font color="#{icol.hexval()[2:]}"><b>{icon}</b></font>&nbsp;&nbsp;{text}',
            ParagraphStyle("Kd", parent=styles["Normal"], fontSize=8.5,
                           textColor=DARK_TXT, leading=12, leftIndent=2),
        ))
        story.append(Spacer(1, 0.12*cm))
    story.append(Spacer(1, 0.35*cm))

    _pvm = pvmath_score if pvmath_score is not None else _suit.get("pvmath_score", _suit["overall"])
    _pvm_verdict = pvmath_verdict or _suit.get("verdict_label", "")
    _bench = benchmark or {}
    story.append(section_hdr("PVMATH SCORE"))
    story.append(Spacer(1, 0.12*cm))
    _pvm_lines = [
        f"<b>PVMath Score:</b> {_pvm}/100",
        f"<b>Verdict:</b> {_pvm_verdict}",
        "<b>Score basis:</b> Deterministic engineering screening model",
        f"<b>Benchmark status:</b> {_bench.get('status_message', 'Benchmarking requires more PVMath screening history. Current score is based on deterministic engineering rules.')}",
    ]
    for line in _pvm_lines:
        story.append(Paragraph(
            line,
            ParagraphStyle("PvmSc", parent=styles["Normal"], fontSize=9,
                           textColor=DARK_TXT, leading=13),
        ))
    story.append(Spacer(1, 0.35*cm))

    story.append(section_hdr("KEY METRICS"))
    story.append(Spacer(1, 0.15*cm))

    def _badge(text):
        """Colour-coded rating badge matching website style."""
        _t = text.split("—")[0].strip().upper()
        if any(w in _t for w in ["EXCELLENT", "VERY GOOD", "GOOD", "LOW"]):
            return lp(f"<b>{_t}</b>", C_GREEN, bold=True, size=8)
        if any(w in _t for w in ["ACCEPTABLE","MODERATE","LOW-MOD","INDICATIVE","DATA UNAVAILABLE"]):
            return lp(f"<b>{_t}</b>", C_YELLOW, bold=True, size=8)
        if any(w in _t for w in ["CHALLENGING","HIGH"]):
            return lp(f"<b>{_t}</b>", C_ORANGE, bold=True, size=8)
        if any(w in _t for w in ["CRITICAL","VERY HIGH"]):
            return lp(f"<b>{_t}</b>", C_RED, bold=True, size=8)
        return lp(text, MUTED, size=8)

    _slope_badge = _badge(slope_lbl)
    _solar_badge = _badge(solar_lbl)
    _flood_badge = _badge(flood_risk.replace("🟢 ", "").replace("🟡 ", "").replace("🟠 ", "").replace("🔴 ", "").replace("⚠️ ", ""))
    _yield_lbl = "Specific Yield"
    _yield_rating = f"{SCREENING_LOSS_PCT:.0f}% flat loss; no row-shading"
    _incentive_lbl = _incentive_row_label(project_country, country)
    _cap_mwp = format_mwp_range(cap["mwp_lo"], cap["mwp_hi"])
    _cap_dens = format_capacity_rating(cap)
    _output_val = format_mwh_range(cap["mwh_lo"], cap["mwh_hi"]) or "— (yield data unavailable)"

    rows = [
        [lp("Metric",          colors.white, bold=True, size=9),
         lp("Value",           colors.white, bold=True, size=9),
         lp("Rating",          colors.white, bold=True, size=9)],
        [lp("In-plane Irradiation", MUTED, size=9), lp(f"{solar.get('annual_ghi','—')} kWh/m²/yr", bold=True, size=9),   _solar_badge],
        [lp(_yield_lbl,       MUTED, size=9), lp(f"{solar.get('annual_yield','—')} kWh/kWp/yr", bold=True, size=9), lp(_yield_rating, MUTED, size=8)],
    ]
    if mount_type == "Single-Axis Tracker":
        rows.append([lp("Mounting", MUTED, size=9), lp("Single-axis tracker (horizontal N–S axis)", bold=True, size=9), lp("—", MUTED, size=8)])
    else:
        rows.append([lp("Optimal Tilt", MUTED, size=9), lp(f"{solar.get('optimal_tilt','—')}°", bold=True, size=9), lp("—", MUTED, size=8)])
    _flood_val = flood_reason or flood_detail or "—"

    _slope_metric_lbl = "Mean Slope" if terrain.get("topoiq_confirmed") else "Max Slope"
    _slope_metric_val = (
        terrain.get("mean_slope_pct") if terrain.get("topoiq_confirmed")
        else terrain.get("max_slope_pct", "—")
    )

    rows += [
        [lp(_slope_metric_lbl, MUTED, size=9), lp(f"{_slope_metric_val}%", bold=True, size=9),        _slope_badge],
        [lp("Elevation",       MUTED, size=9), lp(f"{terrain.get('center_elev','—')} m asl", bold=True, size=9),     lp("—", MUTED, size=8)],
        [lp("Flood Risk",      MUTED, size=9), lp(_flood_val, size=9),                            _flood_badge],
        [lp("Est. DC Capacity", MUTED, size=9), lp(_cap_mwp, bold=True, size=9),               lp(_cap_dens, MUTED, size=8)],
        [lp("Est. Output",     MUTED, size=9), lp(_output_val, bold=True, size=9),                                    lp("Indicative only", MUTED, size=8)],
        [lp(_incentive_lbl,   MUTED, size=9), lp(eeg_status, bold=True, size=9),                                    lp(eeg_note, MUTED, size=8)],
    ]
    mt = Table(rows, colWidths=[4.5*cm, 5.5*cm, 7*cm])
    mt.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0), ORANGE),
        ("FONTSIZE",      (0,0),(-1,-1), 9),
        ("BOX",           (0,0),(-1,-1), 0.5, BORDER),
        ("INNERGRID",     (0,0),(-1,-1), 0.4, BORDER),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, LGRAY]),
        ("TOPPADDING",    (0,0),(-1,-1), 7),
        ("BOTTOMPADDING", (0,0),(-1,-1), 7),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]))
    story.append(mt)

    if flood_source or flood_confidence:
        story.append(Spacer(1, 0.1*cm))
        _flood_meta = " ".join(
            p for p in (
                f"Source: {flood_source}" if flood_source else "",
                f"Confidence: {flood_confidence}" if flood_confidence else "",
            ) if p
        )
        story.append(Paragraph(
            _flood_meta,
            ParagraphStyle("FloodMeta", parent=styles["Normal"], fontSize=7, textColor=MUTED, leading=10),
        ))

    _cap_note_style = ParagraphStyle(
        "CapNote", parent=styles["Normal"], fontSize=8,
        textColor=MUTED, leading=11,
    )
    story.append(Spacer(1, 0.15*cm))
    story.append(Paragraph(capacity_basis_sentence(cap), _cap_note_style))
    story.append(Spacer(1, 0.08*cm))
    story.append(Paragraph(capacity_footnote_global(), _cap_note_style))
    story.append(Spacer(1, 0.08*cm))
    if solar.get("success"):
        _scr_y = solar.get("annual_yield")
        _ana_y = analysis_ref.get("spec_y") if analysis_ref else None
        _gcr = analysis_ref.get("gcr") if analysis_ref else None
        story.append(Paragraph(
            yield_cross_ref_pdf_text(_scr_y, _ana_y, mount_type, gcr=_gcr or 0.30),
            _cap_note_style,
        ))

    if terrain.get("success"):
        if terrain.get("topoiq_confirmed"):
            _gp = terrain.get("sample_points", 0)
            _gm = terrain.get("grid_m", 0)
            _slope_note = (
                f"<b>Terrain confirmed via TopoIQ</b> — mean slope {terrain.get('mean_slope_pct','—')}%, "
                f"max {terrain.get('max_slope_pct','—')}% from {_gp:,} Copernicus GLO-30 grid points "
                f"at {float(_gm):.0f} m across the project boundary."
            )
            _slope_note_color = C_GREEN
            _slope_note_bg = C_LGREEN
        elif terrain.get("boundary_sampled"):
            _slope_note = (
                f"<b>Slope is indicative only</b> — assessed from {terrain.get('sample_points','—')} sparse "
                f"OpenTopoData sample points across the drawn boundary "
                f"({terrain.get('pct_over5','—')}% of samples &gt;5% slope, "
                f"{terrain.get('pct_over10','—')}% &gt;10%). "
                f"Do <b>not</b> treat the Max Slope rating as confirmed until TopoIQ has been run."
            )
            _slope_note_color = C_ORANGE
            _slope_note_bg = C_LORANG
        else:
            _slope_note = (
                f"Slope estimated from {terrain.get('sample_points','—')} elevation samples within a 500m radius "
                "of the pin (no site boundary drawn). Run TopoIQ for full-resolution terrain analysis."
            )
            _slope_note_color = MUTED
            _slope_note_bg = None
        story.append(Spacer(1, 0.15*cm))
        _slope_style = ParagraphStyle(
            "SlopeNote", parent=styles["Normal"], fontSize=8,
            textColor=_slope_note_color,
            leading=11,
            backColor=_slope_note_bg,
            borderPadding=6,
        )
        story.append(Paragraph(_slope_note, _slope_style))

    story.append(Spacer(1, 0.5*cm))

    # ── Monthly Irradiation Bar Chart ────────────────────────────────────────
    monthly_data = solar.get("monthly", [])
    if monthly_data:
        _chart_header = section_hdr("MONTHLY SOLAR IRRADIATION (kWh/m²)")

        months_abbr = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        ghi_vals = [row.get("GHI (kWh/m²)", 0) for row in monthly_data[:12]]
        max_ghi  = max(ghi_vals) if ghi_vals else 1

        # ── ReportLab bar chart drawing ───────────────────────────────────────
        from reportlab.lib.units import cm as _cm
        _chart_w  = 17 * _cm   # full page width
        _chart_h  = 5  * _cm   # bar area height
        _pad_l    = 1.2* _cm   # left padding for y-axis labels
        _pad_b    = 1.2* _cm   # bottom for month labels
        _pad_r    = 0.3* _cm
        _pad_t    = 0.3* _cm
        _n        = len(ghi_vals)
        _bar_area_w = _chart_w - _pad_l - _pad_r
        _bar_area_h = _chart_h - _pad_b - _pad_t
        _bar_w    = _bar_area_w / _n * 0.62
        _gap      = _bar_area_w / _n

        d = Drawing(_chart_w, _chart_h)

        # Grid lines (4 horizontal)
        for _gi, _gv in enumerate([0.25, 0.5, 0.75, 1.0]):
            _gy = _pad_b + _bar_area_h * _gv
            d.add(Line(_pad_l, _gy, _chart_w - _pad_r, _gy,
                       strokeColor=colors.HexColor("#d4e0d4"), strokeWidth=0.5))
            _gl = f"{int(max_ghi * _gv)}"
            d.add(String(_pad_l - 4, _gy - 3, _gl,
                         fontSize=6, fillColor=colors.HexColor("#5a7a5a"),
                         textAnchor="end"))

        # Bars + month labels + value labels
        for _i, (_m, _v) in enumerate(zip(months_abbr, ghi_vals)):
            _ratio   = _v / max_ghi if max_ghi else 0
            _bh      = _bar_area_h * _ratio
            _bx      = _pad_l + _i * _gap + (_gap - _bar_w) / 2
            _by      = _pad_b

            # Rainbow by month position (red winter → green summer)
            _bar_col = colors.HexColor(_MONTH_COLORS[_i % 12])

            d.add(Rect(_bx, _by, _bar_w, _bh,
                       fillColor=_bar_col, strokeColor=None))

            # Month label below bar
            d.add(String(_bx + _bar_w/2, _pad_b - 10, _m,
                         fontSize=7, fillColor=colors.HexColor("#1a2e1a"),
                         textAnchor="middle"))

            # Value label on top of bar (only if bar is tall enough)
            if _bh > 10:
                d.add(String(_bx + _bar_w/2, _by + _bh + 2, f"{int(_v)}",
                             fontSize=6.5, fillColor=colors.HexColor("#0d1a0d"),
                             textAnchor="middle"))

        # Baseline
        d.add(Line(_pad_l, _pad_b, _chart_w - _pad_r, _pad_b,
                   strokeColor=colors.HexColor("#d4e0d4"), strokeWidth=1))

        _sub = Paragraph(
            f"Peak month: {months_abbr[ghi_vals.index(max_ghi)]} ({max_ghi:.0f} kWh/m²)  |  "
            f"Annual total: {sum(ghi_vals):.0f} kWh/m²",
            ParagraphStyle("sub", parent=styles["Normal"], fontSize=8, textColor=colors.grey)
        )
        story.append(KeepTogether([_chart_header, Spacer(1, 0.15*cm), d, Spacer(1, 0.2*cm), _sub]))
        story.append(Spacer(1, 0.5*cm))

    story.append(section_hdr("RECOMMENDED NEXT STEPS"))
    story.append(Spacer(1, 0.15*cm))
    for step in get_next_steps(project_country or country, land_use, lat=lat, lon=lon):
        story.append(Paragraph(step,
            ParagraphStyle("step", parent=styles["Normal"], fontSize=9,
                           textColor=DARK_TXT, leading=13, leftIndent=4)))
        story.append(Spacer(1, 0.2*cm))

    story.append(Spacer(1, 0.3*cm))

    story.append(section_hdr("REFERENCE"))
    story.append(Spacer(1, 0.12*cm))
    story.append(Paragraph(
        "<b>Verdict scale:</b> Excellent &gt; Very Good &gt; Good &gt; Acceptable &gt; Challenging &gt; Critical",
        ParagraphStyle("VScale", parent=styles["Normal"], fontSize=8, textColor=MUTED, leading=11),
    ))
    story.append(Spacer(1, 0.25*cm))

    flood_rows = [
        [lp("Flood risk", colors.white, bold=True, size=7), lp("Meaning", colors.white, bold=True, size=7)],
        [lp("LOW",            C_GREEN,  bold=True, size=7), lp("Elevated terrain — verify at local portal", MUTED, size=7)],
        [lp("LOW-MODERATE",   C_YELLOW, bold=True, size=7), lp("Moderate elevation — check watercourses", MUTED, size=7)],
        [lp("MODERATE",       C_ORANGE, bold=True, size=7), lp("Low-lying — manual flood check required", MUTED, size=7)],
        [lp("HIGH",           C_RED,    bold=True, size=7), lp("Very low elevation — official zone study", MUTED, size=7)],
    ]
    ft = Table(flood_rows, colWidths=[3.2*cm, 13.8*cm])
    ft.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  ORANGE),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.lightgrey),
        ("TOPPADDING",    (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, LGRAY]),
        ("BACKGROUND",    (0,1), (0,1), C_LGREEN),
        ("BACKGROUND",    (0,2), (0,2), C_LYELLOW),
        ("BACKGROUND",    (0,3), (0,3), C_LORANG),
        ("BACKGROUND",    (0,4), (0,4), C_LRED),
    ]))
    story.append(ft)

    story.append(Spacer(1, 0.35*cm))
    append_pdf_disclaimer(story, SITEIQ_DISCLAIMER_BODY)
    append_pdf_footer(
        story,
        "SiteIQ",
        data_sources="PVGIS JRC (EU Commission), EU-DEM / SRTM (OpenTopoData), OpenStreetMap (Nominatim).",
        note="Pre-feasibility screening only — not a substitute for a bankable energy study. ",
        muted_color=MUTED,
        border_color=BORDER,
    )

    doc.build(story)
    buf.seek(0)
    return buf


# ─── UI Layout ────────────────────────────────────────────────────────────────

# ── Shared project context ──────────────────────────────────────────────────
_proj       = st.session_state.get("pvm_project", {})
if _proj.get("topoiq_cache"):
    st.session_state.setdefault("topoiq_run_cache", _proj["topoiq_cache"])
_proj_name  = _proj.get("name", "")
_proj_ctry  = _proj.get("country", "")
_proj_lat   = _proj.get("lat")
_proj_lon   = _proj.get("lon")
_has_proj   = _proj_lat is not None and _proj_lon is not None
_boundaries = _boundaries_from_project(_proj) if _has_proj else []
_enabled_polys_latlon = _enabled_polygons_latlon(_boundaries)
_enabled_n = sum(1 for b in _boundaries if b.get("enabled"))

if _has_proj:
    st.markdown(f"""
    <div style="background:#e8f5ee;border:1px solid #b8ddc8;border-radius:8px;
                padding:0.65rem 1rem;margin-bottom:0.9rem;font-size:0.89rem;color:#1a3a1a;">
      <strong>📋 Project:</strong>&nbsp; {_proj_name}
      &nbsp;·&nbsp; {_proj_ctry}
      &nbsp;·&nbsp; {format_coords(_proj_lat, _proj_lon)}
    </div>
    """, unsafe_allow_html=True)
    # Pre-centre the map and pre-populate coordinates from project context
    if "map_center" not in st.session_state:
        st.session_state["map_center"] = [_proj_lat, _proj_lon]
        st.session_state["map_zoom"]   = 13
    if "map_lat" not in st.session_state:
        st.session_state["map_lat"] = _proj_lat
        st.session_state["map_lon"] = _proj_lon

pd_col1, pd_col2 = st.columns(2)
with pd_col1:
    st.markdown(f"**Project:** {_proj_name or '—'}")
with pd_col2:
    st.markdown(f"**Country:** {_proj_ctry or '—'}")
if not _has_proj:
    st.info(
        "Set up a project in **Project Setup** first — location, boundary, and area are entered there once.",
        icon="ℹ️",
    )

st.divider()

st.markdown("**Site screening configuration**")
_siq_lu_col, _siq_mt_col = st.columns(2)
with _siq_lu_col:
    _lu_default = st.session_state.get("siteiq_land_use", "Standard")
    _lu_ix = 1 if _lu_default == "Agri-PV" else 0
    _land_use_sel = st.radio(
        "Land use",
        ["Standard Ground Mount", "Agri-PV (Dual Use)"],
        index=_lu_ix,
        horizontal=True,
        key="siteiq_land_use_radio",
        help="Used for regulatory flags, capacity density, and slope thresholds in this SiteIQ run.",
    )
with _siq_mt_col:
    _mt_default = st.session_state.get("siteiq_mount_type", "Fixed Tilt")
    _mt_ix = 1 if _mt_default == "Single-Axis Tracker" else 0
    _mount_type_sel = st.radio(
        "Mounting system",
        ["Fixed Tilt", "Single-Axis Tracker"],
        index=_mt_ix,
        horizontal=True,
        key="siteiq_mount_type_radio",
        help="SiteIQ assesses slope and capacity for the system you select here.",
    )
_land_use = "Agri-PV" if "Agri-PV" in _land_use_sel else "Standard"
_mount_type = _mount_type_sel
st.session_state["siteiq_land_use"] = _land_use
st.session_state["siteiq_mount_type"] = _mount_type
_land_display = "Agri-PV (Dual Use)" if _land_use == "Agri-PV" else "Standard Ground Mount"
_mount_display = _mount_type

st.divider()

left, right = st.columns([1, 2])

project_name = _proj_name
project_country_input = _proj_ctry

go_clicked = False

with left:
    st.subheader("📍 Site Location")

    lat = lon = None
    kml_area = None

    if not _has_proj:
        st.warning(
            "No project location yet. Open **Project Setup**, enter your site (pin, coordinates, "
            "or KMZ), and save — then return here to run SiteIQ."
        )
        if st.button("Go to Project Setup", type="primary", use_container_width=True, key="siq_go_proj"):
            st.switch_page("pages/project.py")

    elif _enabled_polys_latlon:
        _lat_c, _lon_c = _boundary_center(_enabled_polys_latlon)
        lat, lon = _lat_c, _lon_c
        all_lats = [p[0] for poly in _enabled_polys_latlon for p in poly]
        all_lons = [p[1] for poly in _enabled_polys_latlon for p in poly]
        _vert_n = sum(len(poly) for poly in _enabled_polys_latlon)

        st.markdown(
            f'<div style="background:#e8f5ee;border:1.5px solid #b8ddc8;border-radius:10px;'
            f'padding:0.75rem 1rem;margin-bottom:0.6rem;">'
            f'<span style="font-weight:700;color:#145f34;font-size:0.88rem;">'
            f'<i class="fa-solid fa-circle-check"></i> Site boundary from Project Setup</span><br>'
            f'<span style="font-size:0.8rem;color:#3a5a3a;">'
            f'{_enabled_n} enabled parcel{"s" if _enabled_n != 1 else ""} · '
            f'{_vert_n} vertices &nbsp;·&nbsp; '
            f'Centre {format_coords(_lat_c, _lon_c)}</span>'
            f'</div>',
            unsafe_allow_html=True
        )
        m = folium.Map(location=[_lat_c, _lon_c], zoom_start=14,
                       tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                       attr="Google Satellite")
        for poly in _enabled_polys_latlon:
            folium.Polygon(
                locations=[(c[0], c[1]) for c in poly],
                color="#22c55e", fill=True, fill_opacity=0.25, weight=3,
            ).add_to(m)
        st_folium(m, width=None, height=340, returned_objects=[])
        st.caption("Read-only preview — edit parcels in **Project Setup**.")
        st.success(f"📌 {format_coords(lat, lon)} · site boundary centre")

    elif _proj.get("mode") == "full" and _boundaries and _enabled_n == 0:
        st.warning(
            "No parcels enabled. Open **Project Setup**, check the parcels you want, and save."
        )
        lat = _proj_lat
        lon = _proj_lon

    elif _has_proj:
        lat = _proj_lat
        lon = _proj_lon
        center = [_proj_lat, _proj_lon]
        zoom   = st.session_state.get("map_zoom", 13)

        m = folium.Map(location=center, zoom_start=zoom,
                       tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                       attr="Google Satellite")
        folium.Marker([lat, lon], tooltip="Project site",
                      icon=folium.Icon(color="green", icon="star")).add_to(m)

        st_folium(m, width=None, height=340, returned_objects=[])
        st.success(f"📌 {format_coords(lat, lon)} · reference pin")

    if _has_proj and _proj.get("area_ha"):
        area_ha = float(_proj["area_ha"])
        st.metric("Site area (ha)", f"{area_ha:,.1f}")
    elif _has_proj:
        area_ha = st.number_input(
            "Site area (ha)",
            min_value=0.1,
            value=float(_proj.get("area_ha") or 10.0),
            step=0.5,
            help="Set area in Project Setup to auto-fill here on future visits.",
        )
    else:
        area_ha = 10.0

    _used = is_over_limit(_username, "siteiq")
    _left = remaining(_username, "siteiq")

    if is_over_limit(_username, "siteiq"):
        _pw_title, _pw_body = limit_reached_message(_username, "SiteIQ")
        st.markdown(f"""
        <div style="background:#fff;border:1.5px solid #e2ede2;border-radius:14px;
                    padding:1.8rem 1.6rem;text-align:center;margin-top:0.5rem;
                    font-family:'Inter',sans-serif;">
          <div style="font-size:2rem;margin-bottom:0.5rem;">🔒</div>
          <div style="font-size:1.2rem;font-weight:800;color:#1a5c2e;margin-bottom:0.4rem;">
            {_pw_title}
          </div>
          <div style="color:#555;font-size:0.88rem;margin-bottom:1.2rem;line-height:1.6;">
            {_pw_body}
          </div>
          <a href="{UPGRADE_CONTACT}"
             style="display:inline-block;background:linear-gradient(135deg,#1d9e52,#145f34);
                    color:#fff;font-weight:700;font-size:0.95rem;padding:0.75rem 2rem;
                    border-radius:9px;text-decoration:none;letter-spacing:0.01em;">
            Contact us to upgrade →
          </a>
          <div style="margin-top:1rem;font-size:0.78rem;color:#999;">
            Questions? <a href="mailto:contact@pvmath.com" style="color:#1d9e52;">contact@pvmath.com</a>
          </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        if _left <= 1:
            st.warning(f"⚠️ {_left} free analysis remaining after this run.")
        _has_topo_cache = topo_cache_valid_for_siteiq(
            get_topo_cache(st.session_state, _proj),
            _proj,
            st.session_state.get("pvm_project_row_id"),
        )
        if _enabled_polys_latlon and _has_topo_cache:
            st.caption("Confirmed TopoIQ terrain is available — this screening will use GLO-30 grid results.")
        elif _enabled_polys_latlon:
            st.caption(
                "Tip: run **TopoIQ** on this boundary first — SiteIQ will then use confirmed "
                "terrain instead of a sparse sample."
            )
        go_clicked = st.button(
            "🔍 Run Site Screening",
            type="primary",
            use_container_width=True,
            disabled=not _has_proj,
        )

with right:
    # st.button() only returns True on the single rerun right after the click —
    # it's False again on every later rerun. The results section used to be
    # gated directly on that raw value, so clicking the "Download PDF" button
    # below (itself a rerun-triggering click) made `go` False again and the
    # whole results section — including the just-rendered download button —
    # collapsed back to the placeholder/legacy view, immediately, with no
    # browser Back press involved. Fix: snapshot everything the results need
    # into st.session_state on a real "Run Site Screening" click, and keep
    # rendering from that snapshot on every subsequent rerun until the next
    # real click replaces it. Network calls + increment_usage() only run on
    # go_clicked itself, never on a redisplay-from-cache rerun, so usage isn't
    # double-counted by clicking Download PDF or anything else on the page.
    _run_cache = st.session_state.get("siteiq_run_cache")
    if not is_over_limit(_username, "siteiq") and (go_clicked or _run_cache):
        if go_clicked:
            if lat is None or lon is None:
                st.error("Set up a project with a site location in **Project Setup** first.")
                st.stop()

            st.session_state["siteiq_project_name"] = project_name or "Unnamed Project"
            st.session_state["siteiq_country"]      = project_country_input or ""
            st.session_state["siteiq_lat"]          = lat
            st.session_state["siteiq_lon"]          = lon
            st.session_state["siteiq_area_ha"]      = area_ha

            _coord_note = "Site boundary centre" if _enabled_polys_latlon else "Reference pin"
            _location_label = resolve_location_label(
                lat, lon,
                saved_label=_proj.get("location_label", ""),
                country=project_country_input or _proj.get("country", ""),
            )

            increment_usage(_username, "siteiq")

            with st.spinner("Fetching solar resource data from EU PVGIS…"):
                solar = get_solar_data(lat, lon, _mount_type)
            _analysis_ref = None
            if solar.get("success"):
                with st.spinner("Fetching YieldIQ analysis reference for cross-check…"):
                    _analysis_ref = fetch_analysis_reference(
                        lat, lon, _mount_type,
                        raddatabase=solar.get("radiation_db"),
                    )
            with st.spinner("Analysing terrain & slope…"):
                terrain, _used_topo_cache = resolve_terrain_for_siteiq(
                    lat, lon,
                    polygons=_enabled_polys_latlon if _enabled_polys_latlon else None,
                    project=_proj,
                    project_row_id=st.session_state.get("pvm_project_row_id"),
                    session_state=st.session_state,
                    fetch_sparse=lambda la, lo, polygons=None: get_terrain_data(
                        la, lo, polygons=polygons
                    ),
                )

            st.session_state["siteiq_run_cache"] = {
                "lat": lat, "lon": lon, "area_ha": area_ha,
                "project_name": project_name, "project_country_input": project_country_input,
                "land_use": _land_use, "mount_type": _mount_type,
                "solar": solar, "terrain": terrain,
                "analysis_ref": _analysis_ref,
                "location_label": _location_label, "coord_note": _coord_note,
                "used_topo_cache": _used_topo_cache,
            }
        else:
            # Redisplay-from-cache rerun (e.g. triggered by clicking Download
            # PDF) — restore the frozen inputs/results from the last real run
            # instead of re-fetching or re-incrementing usage.
            lat, lon, area_ha          = _run_cache["lat"], _run_cache["lon"], _run_cache["area_ha"]
            project_name               = _run_cache["project_name"]
            project_country_input      = _run_cache["project_country_input"]
            _land_use                  = _run_cache["land_use"]
            _mount_type                = _run_cache["mount_type"]
            solar, terrain              = _run_cache["solar"], _run_cache["terrain"]
            _analysis_ref              = _run_cache.get("analysis_ref")
            _location_label            = _run_cache.get("location_label", _proj.get("location_label", ""))
            _coord_note                = _run_cache.get("coord_note", "")

        _sparse_slope = bool(
            terrain.get("success")
            and terrain.get("boundary_sampled")
            and not terrain.get("topoiq_confirmed")
        )
        _slope_pct = (
            terrain.get("mean_slope_pct")
            if terrain.get("topoiq_confirmed")
            else terrain.get("max_slope_pct")
        ) if terrain.get("success") else 0
        s_lbl, _, s_detail = assess_slope(
            _slope_pct,
            _mount_type,
            sparse_screening=_sparse_slope,
            sample_points=terrain.get("sample_points", 0) if terrain.get("success") else 0,
        )
        if terrain.get("topoiq_confirmed"):
            _gp = terrain.get("sample_points", 0)
            _gm = terrain.get("grid_m", 0)
            s_detail = (
                f"TopoIQ confirmed — mean slope {terrain['mean_slope_pct']:.1f}%, "
                f"max {terrain['max_slope_pct']:.1f}% ({_gp:,} GLO-30 grid points at {_gm:.0f} m)."
            )
        if solar["success"]:
            g_lbl, _, g_detail = assess_solar(solar["annual_ghi"])
        else:
            # Don't report a fabricated "0 kWh/m² — Poor" verdict when the PVGIS
            # call itself failed — that reads as a real (and possibly very wrong)
            # site assessment. Surface it as a data error instead.
            g_lbl, g_detail = "⚠️ Data unavailable", "Solar resource data could not be retrieved for this location — try again or check PVGIS coverage."
        country, eeg_status, eeg_note = assess_eeg(lat, lon, _land_use, project_country_input)
        _yield = solar.get("annual_yield") if solar.get("success") else None
        cap = screening_capacity(area_ha, _land_use, _mount_type, _yield)
        verdict, verdict_txt = overall_verdict(
            s_lbl, g_lbl, _land_use, _mount_type,
            slope_pct=_slope_pct if terrain.get("success") else None,
            sparse_screening=_sparse_slope,
            sample_points=terrain.get("sample_points", 0) if terrain.get("success") else 0,
        )
        _flood = get_flood_risk(
            lat, lon, terrain.get("center_elev") if terrain.get("success") else None
        )
        flood_risk = _flood["risk"]
        flood_detail = _flood["detail"]
        flood_portal = _flood["portal"]
        flood_portal_name = _flood["portal_name"]

        _suit_ui = compute_site_suitability(
            g_lbl, s_lbl, flood_risk, _land_use, solar, terrain, _mount_type,
            country=country, eeg_status=eeg_status, project_country=project_country_input,
            cap=cap,
        )
        _pvmath_score = _suit_ui["pvmath_score"]
        _pvmath_verdict = _suit_ui["verdict_label"]
        _benchmark = get_global_benchmark_summary(
            _pvmath_score, project_country_input or country,
        )

        if go_clicked:
            _mod_conf = module_confidence_label("siteiq")
            _record = build_screening_record(
                user_id=_username,
                project_name=project_name,
                lat=lat, lon=lon,
                area_ha=area_ha,
                land_use=_land_use,
                mount_type=_mount_type,
                solar=solar,
                terrain=terrain,
                cap=cap,
                flood=_flood,
                scores=_suit_ui["scores"],
                pvmath_score=_pvmath_score,
                verdict_label=_pvmath_verdict,
                module_confidence=_mod_conf,
                country=country,
                project_country=project_country_input,
                location_label=_location_label,
                eeg_status=eeg_status,
                coord_note=_coord_note,
                project_row_id=st.session_state.get("pvm_project_row_id"),
                used_topo_cache=bool(
                    st.session_state.get("siteiq_run_cache", {}).get("used_topo_cache")
                ),
            )
            _saved_report_id = save_site_screening_result(_record)
            st.session_state["siteiq_run_cache"]["pvmath_score"] = _pvmath_score
            st.session_state["siteiq_run_cache"]["pvmath_verdict"] = _pvmath_verdict
            st.session_state["siteiq_run_cache"]["benchmark"] = _benchmark
            st.session_state["siteiq_run_cache"]["screening_report_id"] = _saved_report_id
            if not _saved_report_id:
                st.caption(
                    "Note: This screening could not be saved to your PVMath library "
                    "(database unavailable). Your report was generated normally."
                )
        elif _run_cache:
            _pvmath_score = _run_cache.get("pvmath_score", _pvmath_score)
            _pvmath_verdict = _run_cache.get("pvmath_verdict", _pvmath_verdict)
            _benchmark = _run_cache.get("benchmark", _benchmark)

        badge_color = "#1a5c2e" if _land_use == "Agri-PV" else "#1565c0"
        st.markdown(
            f'<span style="background:{badge_color};color:white;padding:3px 10px;border-radius:4px;font-size:0.8rem;">'
            f'{_land_display} · {_mount_display}</span>',
            unsafe_allow_html=True
        )
        st.markdown("")

        if terrain.get("topoiq_confirmed"):
            st.success(
                "**Terrain confirmed via TopoIQ** — SiteIQ is using Copernicus GLO-30 grid "
                "analysis from your last TopoIQ run on this boundary."
            )
        elif _sparse_slope and terrain.get("success"):
            st.caption(
                "Slope is from a sparse OpenTopoData sample — run **TopoIQ** on this boundary "
                "for confirmed terrain in SiteIQ."
            )

        if "✅" in verdict:
            st.success(f"**{verdict}** — {verdict_txt}")
        elif "⚠️" in verdict:
            st.warning(f"**{verdict}** — {verdict_txt}")
        else:
            st.error(f"**{verdict}** — {verdict_txt}")

        st.caption(module_confidence_label("siteiq"))

        st.markdown(
            f'<div style="background:#f0f7f2;border:1px solid #c8e6d0;border-radius:10px;'
            f'padding:0.85rem 1rem;margin:0.75rem 0;">'
            f'<div style="font-size:0.72rem;font-weight:800;text-transform:uppercase;'
            f'letter-spacing:0.1em;color:#1d9e52;margin-bottom:0.35rem;">PVMath Score</div>'
            f'<div style="font-size:1.35rem;font-weight:800;color:#1a2e1a;">{_pvmath_score}/100 '
            f'<span style="font-size:0.95rem;color:#1d9e52;">({_pvmath_verdict})</span></div>'
            f'<div style="font-size:0.82rem;color:#4a6a4a;margin-top:0.35rem;">'
            f'Score basis: Deterministic engineering screening model</div>'
            f'<div style="font-size:0.82rem;color:#5a7a5a;margin-top:0.25rem;">'
            f'Benchmark: {_benchmark.get("status_message", "")}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        help_caption("pvmath_score", "site_verdict")

        _cap_display = format_mwp_range(cap["mwp_lo"], cap["mwp_hi"]).replace(" MWp DC", "")
        _cap_unit = (
            f"MWp DC · GCR {cap['gcr_lo']:.2f}–{cap['gcr_hi']:.2f}"
            if cap["gcr_lo"] != cap["gcr_hi"]
            else f"MWp DC · GCR {cap['gcr_lo']:.2f}"
        )

        _mc4_lbl = "Specific Yield" if _mount_type == "Single-Axis Tracker" else "Optimal Tilt"
        if _mount_type == "Single-Axis Tracker":
            _mc4_num = _fmt_metric_num(solar.get("annual_yield"), 1)
            _mc4_unit = "kWh/kWp/yr"
        else:
            _tilt = solar.get("optimal_tilt")
            _mc4_num = _fmt_metric_num(_tilt, 0) if _tilt is not None else "—"
            _mc4_unit = "deg tilt"

        _slope_num = _fmt_metric_num(terrain.get("max_slope_pct") if terrain.get("success") else None, 1)
        if terrain.get("topoiq_confirmed") and terrain.get("success"):
            _slope_lbl = "Mean Slope"
            _slope_num = _fmt_metric_num(terrain.get("mean_slope_pct"), 1)
            _slope_unit = f"% · max {terrain.get('max_slope_pct', '—')}%"
        elif _sparse_slope and terrain.get("success"):
            _slope_lbl = "Sparse Sample Slope"
            _slope_unit = "max % · run TopoIQ"
        else:
            _slope_lbl = "Max Slope"
            _slope_unit = "%"

        _cards = [
            _metric_card_html("fa-sun", "#f5a623", "In-plane Irradiation",
                              _fmt_metric_num(solar.get("annual_ghi"), 1), "kWh/m²/yr"),
            _metric_card_html("fa-mountain", "#5b9bd5", _slope_lbl, _slope_num, _slope_unit),
            _metric_card_html("fa-bolt", "#2ecc71", "Est. DC Capacity", _cap_display, _cap_unit),
            _metric_card_html("fa-ruler-combined", "#a87fd4", _mc4_lbl, _mc4_num, _mc4_unit),
        ]
        st.markdown(f'<div class="metric-grid">{"".join(_cards)}</div>', unsafe_allow_html=True)
        help_caption("ghi")

        _notes = []
        if _proj.get("mode") == "full" and _enabled_polys_latlon:
            _notes.append(
                f"DC capacity from <b>{area_ha:,.2f} ha</b> site boundary. "
                + capacity_basis_sentence(cap) + ". Layout-optimised designs may differ."
            )
        else:
            _notes.append(
                f"DC capacity from manually entered area (<b>{area_ha:,.2f} ha</b>). "
                + capacity_basis_sentence(cap) + "."
            )
            _notes.append(
                "Draw a boundary in Project Setup for boundary-based figures."
            )
        if cap["mwh_lo"] is not None:
            _notes.append(
                f"Est. output <b>{format_mwh_range(cap['mwh_lo'], cap['mwh_hi'])}</b> "
                f"at {_fmt_metric_num(solar.get('annual_yield'), 1)} kWh/kWp/yr — indicative only."
            )
        _notes.append(capacity_footnote_global())
        if terrain.get("success"):
            if terrain.get("topoiq_confirmed"):
                _notes.append(
                    f"Terrain confirmed via TopoIQ: mean <b>{terrain.get('mean_slope_pct', '—')}%</b>, "
                    f"max <b>{terrain.get('max_slope_pct', '—')}%</b> "
                    f"({terrain.get('sample_points', '—'):,} GLO-30 grid points)."
                )
            elif terrain.get("boundary_sampled"):
                _notes.append(
                    f"Sparse sample slope: <b>{terrain.get('max_slope_pct', '—')}%</b> max "
                    f"({terrain.get('sample_points', '—')} points) — not confirmed. "
                    "Run <b>TopoIQ</b> for confirmed terrain metrics."
                )
            else:
                _notes.append(
                    f"Slope from {terrain.get('sample_points', '—')} pin-radius samples — "
                    "draw a boundary or run TopoIQ for site-wide terrain."
                )
        _notes.append(
            "Pre-feasibility screening only — not a substitute for a bankable energy study or confirmed layout."
        )
        _notes.append(profile_description(PROFILE_SCREENING))
        _notes_html = "".join(f"<li>{n}</li>" for n in _notes)

        st.divider()

        d1, d2 = st.columns(2)
        with d1:
            st.markdown('<div class="section-hdr"><i class="fa-solid fa-sun" style="color:#f5a623;"></i> Solar Resource</div>', unsafe_allow_html=True)
            (st.success if "✅" in g_lbl else st.warning if "⚠️" in g_lbl else st.error)(g_detail)
            if solar.get("success") and _mount_type == "Fixed Tilt":
                _tilt_disp = solar.get("optimal_tilt")
                _yield_disp = solar.get("annual_yield")
                if _tilt_disp is not None or _yield_disp is not None:
                    _parts = []
                    if _tilt_disp is not None:
                        _parts.append(f"**Optimal tilt:** {_tilt_disp:.0f}° (PVGIS)")
                    if _yield_disp is not None:
                        _parts.append(f"**Specific yield:** {_yield_disp:,.0f} kWh/kWp/yr")
                    st.markdown("  \n".join(_parts))

            st.markdown('<div class="section-hdr" style="margin-top:0.8rem;"><i class="fa-solid fa-scale-balanced" style="color:#a87fd4;"></i> Regulatory</div>', unsafe_allow_html=True)
            st.info(f"{country}  \n{eeg_status}  \n_{eeg_note}_")
            help_caption("regulatory_flags")

        with d2:
            st.markdown('<div class="section-hdr"><i class="fa-solid fa-mountain" style="color:#5b9bd5;"></i> Terrain & Slope</div>', unsafe_allow_html=True)
            (st.success if "✅" in s_lbl else st.warning if "⚠️" in s_lbl else st.error)(s_detail)

            st.markdown('<div class="section-hdr" style="margin-top:0.8rem;"><i class="fa-solid fa-water" style="color:#4ab0d4;"></i> Flood Risk</div>', unsafe_allow_html=True)
            _flood_body = (
                f"**{flood_risk}**  \n"
                f"**Reason:** {_flood['reason']}  \n"
                f"**Source:** {_flood['source']}  \n"
                f"**Confidence:** {_flood['confidence']}  \n"
                f"[Check {flood_portal_name} ↗]({flood_portal})"
            )
            if "🔴" in flood_risk:
                st.error(_flood_body)
            elif "🟠" in flood_risk or "🟡" in flood_risk or "⚠️" in flood_risk:
                st.warning(_flood_body)
            else:
                st.success(_flood_body)
            help_caption("flood_risk")

        st.divider()
        with st.expander("Rating Scale — what do the colours mean?"):
            st.markdown(SITEIQ_RATING_LEGEND_MD)

        if solar["success"] and solar.get("monthly"):
            st.divider()
            st.markdown('<div class="section-hdr"><i class="fa-solid fa-chart-bar" style="color:#f5a623;"></i> Monthly Solar Irradiation (kWh/m²)</div>', unsafe_allow_html=True)
            # st.bar_chart sorts a string "Month" axis alphabetically (Apr, Aug,
            # Dec, Feb, Jan...) instead of calendar order — build the chart with
            # Altair directly so we can pin the real Jan-Dec sort order, and use
            # a fixed, shorter height so the chart doesn't dominate the page.
            _month_order = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
            # Same seasonal rainbow palette as the PDF's bar chart (_MONTH_COLORS
            # in build_pdf()) — winter red -> summer green -> winter red — so the
            # on-screen chart and the PDF report match instead of looking like
            # two different charts.
            _month_colors = ["#f87171","#fb923c","#facc15","#a3e635","#4ade80","#22c55e",
                              "#22c55e","#4ade80","#a3e635","#facc15","#fb923c","#f87171"]
            _chart_df = pd.DataFrame(solar["monthly"])
            _irr_chart = (
                alt.Chart(_chart_df)
                .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                .encode(
                    x=alt.X("Month:N", sort=_month_order, title=None,
                            axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("GHI (kWh/m²):Q", title=None),
                    color=alt.Color("Month:N", sort=_month_order,
                                     scale=alt.Scale(domain=_month_order, range=_month_colors),
                                     legend=None),
                    tooltip=["Month", "GHI (kWh/m²)"],
                )
                .properties(height=220)
            )
            st.altair_chart(_irr_chart, use_container_width=True)

        st.divider()
        pdf = build_pdf(
            site_name=project_name or f"Project_{lat:.3f}_{lon:.3f}",
            lat=lat, lon=lon, area_ha=area_ha,
            solar=solar, terrain=terrain,
            country=country, eeg_status=eeg_status, eeg_note=eeg_note,
            slope_lbl=s_lbl, solar_lbl=g_lbl,
            verdict=verdict, verdict_txt=verdict_txt,
            cap=cap,
            land_use=_land_use, mount_type=_mount_type,
            project_country=project_country_input,
            location_label=_location_label,
            flood_risk=flood_risk, flood_detail=flood_detail,
            flood_source=_flood["source"], flood_confidence=_flood["confidence"],
            flood_reason=_flood["reason"],
            coord_note=_coord_note,
            prepared_by=prepared_by_line(),
            module_confidence=module_confidence_label("siteiq"),
            analysis_ref=_analysis_ref,
            pvmath_score=_pvmath_score,
            pvmath_verdict=_pvmath_verdict,
            benchmark=_benchmark,
        )
        st.download_button(
            label="⬇️  Download PDF Report",
            data=pdf,
            file_name=f"SiteIQ_{(project_name or 'report').replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True
        )
        st.markdown(
            f'<div class="siq-screening-notes">'
            f'<div class="siq-notes-kicker">Screening notes</div>'
            f'<ul>{_notes_html}</ul></div>',
            unsafe_allow_html=True,
        )
        if solar.get("success") and _analysis_ref:
            st.markdown(
                yield_cross_ref_siteiq_html(
                    solar["annual_yield"], _analysis_ref, _mount_type,
                ),
                unsafe_allow_html=True,
            )

    else:
        st.caption("Enter a site location on the left and click **Run Site Screening** to get:")
        wc1, wc2 = st.columns(2)
        _wcards = [
            (wc1, "Solar resource",
             "In-plane irradiation · monthly chart · yield by mounting type"),
            (wc2, "Terrain & slope",
             "Max slope % · centre elevation · tracker suitability"),
            (wc1, "Regulatory check",
             "Country-specific incentives · grid authority · permitting contacts"),
            (wc2, "Flood risk",
             "Elevation-based assessment · local flood portal links"),
            (wc1, "Capacity estimate",
             "MWp DC & annual MWh · density by system type"),
            (wc2, "PDF report",
             "One-click download · professional format · screening-grade PDF"),
        ]
        for _col, _title, _desc in _wcards:
            _col.markdown(
                f'<div class="topo-feature-card">'
                f'<div class="topo-feature-title">{_title}</div>'
                f'<div class="topo-feature-desc">{_desc}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        st.caption("Data: PVGIS JRC · EU-DEM / SRTM via OpenTopoData · OpenStreetMap  |  SiteIQ by PVMath — Module 1 of 3 · pvmath.com")
