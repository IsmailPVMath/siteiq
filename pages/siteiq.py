import streamlit as st
import requests
import pandas as pd
import math
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
import folium
from pvmath_auth import (
    show_paywall,
    increment_usage, is_over_limit, remaining, FREE_LIMIT, STRIPE_LINK
)
from pvmath_styles import inject_styles
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

    if elevation is None:
        return "⚠️ Unknown", "Elevation data unavailable — manual check required", portal, portal_name
    elif elevation < 10:
        risk, detail = "🔴 High Risk", f"Elevation {elevation}m — Very low-lying terrain, high flood exposure likely"
    elif elevation < 50:
        risk, detail = "🟠 Moderate Risk", f"Elevation {elevation}m — Low terrain, check official flood maps"
    elif elevation < 200:
        risk, detail = "🟡 Low-Moderate Risk", f"Elevation {elevation}m — Moderate terrain, verify local watercourse proximity"
    else:
        risk, detail = "🟢 Low Risk", f"Elevation {elevation}m — Elevated terrain, flood risk likely low"

    return risk, detail, portal, portal_name


def _fetch_pvgis(lat, lon, raddatabase=None):
    """One PVcalc call. raddatabase=None lets PVGIS auto-pick (PVGIS-SARAH2),
    which only covers roughly -66° to 66° longitude (Europe/Africa/most of Asia)
    — most of India (68-97°E) falls outside it and the call fails/errors."""
    params = {
        "lat": lat, "lon": lon,
        "peakpower": 1, "loss": 14,
        "outputformat": "json",
        "mountingplace": "free",
        "optimalangles": 1,
    }
    if raddatabase:
        params["raddatabase"] = raddatabase
    r = requests.get(
        "https://re.jrc.ec.europa.eu/api/v5_2/PVcalc",
        params=params, timeout=20
    )
    data = r.json()
    totals  = data["outputs"]["totals"]["fixed"]
    monthly = data["outputs"]["monthly"]["fixed"]
    tilt    = data["inputs"]["mounting_system"]["fixed"]["slope"].get("value", "—")

    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    monthly_ghi = [
        {"Month": months[i], "GHI (kWh/m²)": round(m.get("H(i)_m", 0), 1)}
        for i, m in enumerate(monthly[:12])
    ]
    return {
        "success": True,
        "annual_ghi":   round(totals.get("H(i)_y", 0), 1),
        "annual_yield": round(totals.get("E_y", 0), 1),
        "optimal_tilt": tilt,
        "monthly":      monthly_ghi,
    }


def get_solar_data(lat, lon):
    # PVGIS auto-selects PVGIS-SARAH2 by default, which doesn't cover most of
    # India, the Americas, or Australia/Oceania. Falling back to PVGIS-ERA5
    # (true global coverage, coarser resolution) is what actually fixes those
    # regions — previously a failed call here silently became "0 kWh/m²/yr —
    # Poor resource", which read as a real (and very wrong) site assessment
    # for sunny locations like Rajasthan instead of "data unavailable".
    try:
        return _fetch_pvgis(lat, lon)
    except Exception as e1:
        try:
            return _fetch_pvgis(lat, lon, raddatabase="PVGIS-ERA5")
        except Exception as e2:
            return {"success": False, "error": f"{e1} / ERA5 fallback: {e2}"}


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


def get_terrain_data(lat, lon, polygon=None, radius_km=0.5):
    """
    Slope/elevation screening.
    - If `polygon` (the drawn site boundary, [[lat,lon],...]) is supplied, samples a grid
      of points across the ACTUAL boundary — same spirit as TopoIQ's full-grid analysis,
      just coarser — so the verdict reflects the whole site, not just the pin.
    - Otherwise (Quick Mode, pin only), samples a denser 8-direction ring around the pin
      (9 points total, up from the old 4-direction/5-point cross) for the best estimate
      obtainable from a single point.
    """
    in_europe = 34 <= lat <= 72 and -25 <= lon <= 45
    dataset   = "eudem25m" if in_europe else "srtm30m"

    if polygon and len(polygon) >= 3:
        lats = [p[0] for p in polygon]
        lons = [p[1] for p in polygon]
        lat_min, lat_max = min(lats), max(lats)
        lon_min, lon_max = min(lons), max(lons)

        GRID_N = 7
        grid_pts = []
        for i in range(GRID_N):
            for j in range(GRID_N):
                glat = lat_min + (lat_max - lat_min) * (i + 0.5) / GRID_N
                glon = lon_min + (lon_max - lon_min) * (j + 0.5) / GRID_N
                if _point_in_polygon(glat, glon, polygon):
                    grid_pts.append((glat, glon))

        if len(grid_pts) < 4:
            clat, clon = sum(lats) / len(lats), sum(lons) / len(lons)
            grid_pts = list(polygon) + [(clat, clon)]

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


def assess_slope(pct, mount_type="Fixed Tilt"):
    if mount_type == "Single-Axis Tracker":
        if pct <= 3:
            return "✅ Excellent", "green",  f"{pct}% — Ideal for single-axis tracker"
        elif pct <= 6:
            return "⚠️ Acceptable", "yellow", f"{pct}% — Feasible for tracker; grading may be needed"
        elif pct <= 10:
            return "⚠️ Challenging", "yellow", f"{pct}% — Steep for trackers; significant grading required"
        else:
            return "❌ Critical", "red",    f"{pct}% — Too steep for single-axis tracker systems"
    else:
        if pct <= 5:
            return "✅ Excellent", "green",  f"{pct}% — Ideal for fixed-tilt ground mount"
        elif pct <= 10:
            return "⚠️ Acceptable", "yellow", f"{pct}% — Feasible; some earthworks expected"
        elif pct <= 15:
            return "⚠️ Challenging", "yellow", f"{pct}% — Significant earthworks required"
        else:
            return "❌ Critical", "red",    f"{pct}% — Too steep; likely not viable"


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
        return "United States", "ITC 30% + IRA bonus credits applicable", "County zoning permit + utility interconnection agreement required"
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


def site_capacity(area_ha, land_use="Standard", mount_type="Fixed Tilt"):
    if land_use == "Agri-PV":
        density = 0.18 if mount_type == "Single-Axis Tracker" else 0.20
    else:
        density = 0.35 if mount_type == "Single-Axis Tracker" else 0.40
    mw  = round(area_ha * density, 2)
    mwh = round(mw * 1000, 0)
    return mw, mwh


def overall_verdict(slope_lbl, solar_lbl, land_use="Standard", mount_type="Fixed Tilt"):
    reds    = sum(1 for l in [slope_lbl, solar_lbl] if "❌" in l)
    yellows = sum(1 for l in [slope_lbl, solar_lbl] if "⚠️" in l)
    if land_use == "Agri-PV":
        label = f"Agri-PV {mount_type}"
    else:
        label = mount_type
    if reds >= 1:
        return "❌ CRITICAL",     "One or more parameters exceed viability threshold. High risk — reconsider site or system type."
    elif yellows >= 2:
        return "⚠️ CHALLENGING",  "Multiple moderate concerns. Detailed study mandatory before commitment."
    elif yellows == 1:
        return "⚠️ ACCEPTABLE",   f"Site is viable with noted considerations. Address constraints in detailed {label} design."
    else:
        return "✅ EXCELLENT",    f"Strong {label} potential. All parameters in ideal range — proceed to detailed feasibility study."


def get_next_steps(project_country, land_use="Standard"):
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
        steps = [
            "Grid connection: contact local utility / ISO (PJM, CAISO, MISO, ERCOT etc.)",
            "Planning: county zoning permit + conditional use permit (CUP)",
            "Incentives: ITC (Investment Tax Credit) 30% + IRA bonus credits",
            "Environmental: NEPA review if federal land — state-level EIA otherwise",
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


def build_pdf(site_name, lat, lon, area_ha, solar, terrain,
              country, eeg_status, eeg_note,
              slope_lbl, solar_lbl, verdict, verdict_txt,
              cap_mw, cap_mwh,
              land_use="Standard", mount_type="Fixed Tilt",
              project_country=""):
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
        return Paragraph(text, ParagraphStyle("lp", parent=styles["Normal"],
                         fontSize=size, fontName=fn, textColor=color,
                         leading=11, spaceAfter=0))

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
        ["Project Name",   site_name or "—"],
        ["Country",        project_country or country],
        ["Coordinates",    f"{lat:.5f}°N, {lon:.5f}°E"],
        ["Site Area",      f"{area_ha} ha"],
        ["Land Use Type",  land_use],
        ["Mounting System",mount_type],
        ["Report Date",    datetime.now().strftime("%d.%m.%Y")],
    ]
    t = Table(site_rows, colWidths=[5*cm, 12*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(0,-1), colors.HexColor("#e8f5e9")),
        ("FONTNAME",     (0,0),(0,-1), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0),(-1,-1), 10),
        ("GRID",         (0,0),(-1,-1), 0.5, colors.lightgrey),
        ("TOPPADDING",   (0,0),(-1,-1), 6),
        ("BOTTOMPADDING",(0,0),(-1,-1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.5*cm))

    # ── Verdict styling (green/amber/red depending on result) ────────────────
    _is_exc  = "EXCELLENT" in verdict
    _is_acc  = "ACCEPTABLE" in verdict or "CHALLENGING" in verdict
    v_color  = C_GREEN if _is_exc else (C_YELLOW if _is_acc else C_RED)
    v_bg     = C_LGREEN if _is_exc else (C_LYELLOW if _is_acc else C_LRED)
    v_border = GREEN if _is_exc else (C_YELLOW if _is_acc else C_RED)

    story.append(Spacer(1, 0.1*cm))
    story.append(section_hdr("OVERALL VERDICT"))
    story.append(Spacer(1, 0.15*cm))
    vt = Table([[
        Paragraph(f"<b>{verdict}</b>",
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
    story.append(Spacer(1, 0.5*cm))

    story.append(section_hdr("KEY METRICS"))
    story.append(Spacer(1, 0.15*cm))
    _density = (0.18 if land_use=='Agri-PV' and mount_type=='Single-Axis Tracker'
                else 0.20 if land_use=='Agri-PV'
                else 0.35 if mount_type=='Single-Axis Tracker' else 0.40)

    def _badge(text):
        """Colour-coded rating badge matching website style."""
        _t = text.split("—")[0].strip().upper()
        if any(w in _t for w in ["EXCELLENT","GOOD","LOW"]):
            return lp(f"<b>{_t}</b>", C_GREEN, bold=True, size=8)
        if any(w in _t for w in ["ACCEPTABLE","MODERATE","LOW-MOD"]):
            return lp(f"<b>{_t}</b>", C_YELLOW, bold=True, size=8)
        if any(w in _t for w in ["CHALLENGING","HIGH"]):
            return lp(f"<b>{_t}</b>", C_ORANGE, bold=True, size=8)
        if any(w in _t for w in ["CRITICAL","VERY HIGH"]):
            return lp(f"<b>{_t}</b>", C_RED, bold=True, size=8)
        return lp(text, MUTED, size=8)

    _slope_badge = _badge(slope_lbl)
    _solar_badge = _badge(solar_lbl)

    rows = [
        [lp("Metric",          colors.white, bold=True, size=9),
         lp("Value",           colors.white, bold=True, size=9),
         lp("Rating",          colors.white, bold=True, size=9)],
        [lp("Annual GHI",      MUTED, size=9), lp(f"{solar.get('annual_ghi','—')} kWh/m²/yr", bold=True, size=9),   _solar_badge],
        [lp("Annual Yield",    MUTED, size=9), lp(f"{solar.get('annual_yield','—')} kWh/kWp/yr", bold=True, size=9), lp("—", MUTED, size=8)],
        [lp("Optimal Tilt",    MUTED, size=9), lp(f"{solar.get('optimal_tilt','—')}°", bold=True, size=9),           lp("—", MUTED, size=8)],
        [lp("Max Slope",       MUTED, size=9), lp(f"{terrain.get('max_slope_pct','—')}%", bold=True, size=9),        _slope_badge],
        [lp("Elevation",       MUTED, size=9), lp(f"{terrain.get('center_elev','—')} m asl", bold=True, size=9),     lp("—", MUTED, size=8)],
        [lp("Est. Capacity",   MUTED, size=9), lp(f"{cap_mw} MWp", bold=True, size=9),                               lp(f"Density: {_density} MW/ha", MUTED, size=8)],
        [lp("Est. Output",     MUTED, size=9), lp(f"{cap_mwh:,.0f} MWh/yr", bold=True, size=9),                      lp("Indicative only", MUTED, size=8)],
        [lp("EEG / Incentive", MUTED, size=9), lp(eeg_status, bold=True, size=9),                                    lp(eeg_note, MUTED, size=8)],
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

    if terrain.get("success"):
        if terrain.get("boundary_sampled"):
            _slope_note = (
                f"Slope assessed from {terrain.get('sample_points','—')} sample points across the drawn site "
                f"boundary — {terrain.get('pct_over5','—')}% of points &gt;5% slope, "
                f"{terrain.get('pct_over10','—')}% &gt;10%. Run TopoIQ for full-resolution, area-weighted terrain stats."
            )
        else:
            _slope_note = (
                f"Slope estimated from {terrain.get('sample_points','—')} elevation samples within a 500m radius "
                "of the pin (no site boundary drawn). Run TopoIQ for full-resolution terrain analysis."
            )
        story.append(Spacer(1, 0.15*cm))
        story.append(Paragraph(_slope_note,
            ParagraphStyle("SlopeNote", parent=styles["Normal"], fontSize=7, textColor=MUTED, leading=10)))

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
    for step in get_next_steps(project_country or country, land_use):
        story.append(Paragraph(step,
            ParagraphStyle("step", parent=styles["Normal"], fontSize=9,
                           textColor=DARK_TXT, leading=13, leftIndent=4)))
        story.append(Spacer(1, 0.2*cm))

    story.append(Spacer(1, 0.3*cm))

    # ── Rating Legend — small, stacked one below the other for readability ────
    story.append(section_hdr("RATING LEGEND"))

    # Performance ratings table
    perf_rows = [
        [lp("Performance Rating", colors.white, bold=True, size=7), lp("Action", colors.white, bold=True, size=7)],
        [lp("EXCELLENT / GOOD", C_GREEN,  bold=True, size=7), lp("All parameters ideal — proceed", MUTED, size=7)],
        [lp("ACCEPTABLE",       C_YELLOW, bold=True, size=7), lp("Viable with constraints — monitor", MUTED, size=7)],
        [lp("CHALLENGING",      C_ORANGE, bold=True, size=7), lp("Near limit — detailed study required", MUTED, size=7)],
        [lp("CRITICAL",         C_RED,    bold=True, size=7), lp("Exceeds threshold — reconsider site", MUTED, size=7)],
    ]
    pt = Table(perf_rows, colWidths=[3.8*cm, 6.2*cm])
    pt.setStyle(TableStyle([
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

    # Flood risk table
    flood_rows = [
        [lp("Flood Risk Rating", colors.white, bold=True, size=7), lp("Action", colors.white, bold=True, size=7)],
        [lp("LOW RISK",       C_GREEN,  bold=True, size=7), lp("Verify at local flood portal", MUTED, size=7)],
        [lp("LOW-MODERATE",   C_YELLOW, bold=True, size=7), lp("Cross-check official flood maps", MUTED, size=7)],
        [lp("MODERATE RISK",  C_ORANGE, bold=True, size=7), lp("Manual flood risk check required", MUTED, size=7)],
        [lp("HIGH RISK",      C_RED,    bold=True, size=7), lp("Flood zone study before proceeding", MUTED, size=7)],
    ]
    ft = Table(flood_rows, colWidths=[3.8*cm, 6.2*cm])
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

    # Stacked vertically — performance legend, then flood risk legend below
    story.append(pt)
    story.append(Spacer(1, 0.3*cm))
    story.append(ft)

    story.append(Spacer(1, 0.4*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        "Generated by SiteIQ — Solar Site Intelligence Platform by PVMath &nbsp;|&nbsp; pvmath.com &nbsp;|&nbsp; "
        "For professional use only — pre-feasibility screening only, not a substitute for a bankable energy study. "
        "Data: PVGIS JRC (EU Commission), EU-DEM / SRTM (OpenTopoData), OpenStreetMap (Nominatim).",
        ParagraphStyle("Ft", parent=styles["Normal"], fontSize=7, textColor=MUTED, leading=10)
    ))

    doc.build(story)
    buf.seek(0)
    return buf


# ─── UI Layout ────────────────────────────────────────────────────────────────

# ── Shared project context ──────────────────────────────────────────────────
_proj       = st.session_state.get("pvm_project", {})
_proj_name  = _proj.get("name", "")
_proj_ctry  = _proj.get("country", "")
_proj_lat   = _proj.get("lat")
_proj_lon   = _proj.get("lon")
_has_proj   = _proj_lat is not None and _proj_lon is not None

if _has_proj:
    st.markdown(f"""
    <div style="background:#e8f5ee;border:1px solid #b8ddc8;border-radius:8px;
                padding:0.65rem 1rem;margin-bottom:0.9rem;font-size:0.89rem;color:#1a3a1a;">
      <strong>📋 Project:</strong>&nbsp; {_proj_name}
      &nbsp;·&nbsp; {_proj_ctry}
      &nbsp;·&nbsp; {_proj_lat:.5f}°N, {_proj_lon:.5f}°E
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
    project_name = st.text_input("Project Name", value=_proj_name, placeholder="e.g. Bavaria North – Site A")
with pd_col2:
    project_country_input = st.text_input("Project located in (Country)", value=_proj_ctry, placeholder="e.g. Italy, Germany, Spain…")

st.divider()

st.caption("Designed for Ground Mount Solar Projects")
pt_col1, pt_col2 = st.columns(2)

with pt_col1:
    land_use = st.radio(
        "**Land Use**",
        ["Standard", "Agri-PV (Dual Use)"],
        help="Standard = conventional ground-mount. Agri-PV = dual use with agriculture (elevated / bifacial)."
    )
    if land_use == "Agri-PV (Dual Use)":
        st.markdown('<div style="background:#1a5c2e;color:#fff;border-radius:7px;padding:0.45rem 0.8rem;font-size:0.85rem;font-weight:600;">✅ Agri-PV dual-use · Local agricultural regulations apply</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="background:#1565c0;color:#fff;border-radius:7px;padding:0.45rem 0.8rem;font-size:0.85rem;font-weight:600;">ℹ️ Standard ground-mount · No dual-use requirements</div>', unsafe_allow_html=True)

with pt_col2:
    mount_type = st.radio(
        "**Mounting System**",
        ["Fixed Tilt", "Single-Axis Tracker"],
        help="Tracker systems require flatter terrain and more N-S row spacing."
    )
    if mount_type == "Single-Axis Tracker":
        st.markdown('<div style="background:#7a4800;color:#fff;border-radius:7px;padding:0.45rem 0.8rem;font-size:0.85rem;font-weight:600;">⚠️ Tracker: max recommended slope ± 8° · Higher CAPEX, higher yield</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="background:#1565c0;color:#fff;border-radius:7px;padding:0.45rem 0.8rem;font-size:0.85rem;font-weight:600;">ℹ️ Fixed Tilt: max recommended slope ≤ 10% · Lower CAPEX</div>', unsafe_allow_html=True)

_land_use   = "Agri-PV" if "Agri-PV" in land_use else "Standard"
_mount_type = mount_type

st.divider()

left, right = st.columns([1, 2])

with left:
    st.subheader("📍 Site Location")

    lat = lon = None
    kml_area = None

    _proj_polygon_ll = (
        _proj["polygon_coords"]
        if (_proj.get("mode") == "full" and _proj.get("polygon_coords"))
        else None
    )  # project.py stores this as [[lat,lon], ...]

    if _has_proj and _proj_polygon_ll:
        # ── Full Mode project with a drawn boundary — show the actual polygon,
        # same as TopoIQ's "boundary loaded from project" preview, instead of
        # collapsing it to a single point. Read-only here (same as TopoIQ's
        # preloaded view) — go to Project Setup to redraw or clear it.
        lat = _proj_lat
        lon = _proj_lon
        _lons_p = [c[1] for c in _proj_polygon_ll]
        _lats_p = [c[0] for c in _proj_polygon_ll]
        _lon_c  = (min(_lons_p) + max(_lons_p)) / 2
        _lat_c  = (min(_lats_p) + max(_lats_p)) / 2

        st.markdown(
            f'<div style="background:#e8f5ee;border:1.5px solid #b8ddc8;border-radius:10px;'
            f'padding:0.75rem 1rem;margin-bottom:0.6rem;">'
            f'<span style="font-weight:700;color:#145f34;font-size:0.88rem;">'
            f'<i class="fa-solid fa-circle-check"></i> Site boundary loaded from project</span><br>'
            f'<span style="font-size:0.8rem;color:#3a5a3a;">'
            f'{len(_proj_polygon_ll)-1} vertices &nbsp;·&nbsp; '
            f'Centre {_lat_c:.4f}°, {_lon_c:.4f}°</span>'
            f'</div>',
            unsafe_allow_html=True
        )
        m = folium.Map(location=[_lat_c, _lon_c], zoom_start=14,
                       tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                       attr="Google Satellite")
        folium.Polygon(
            locations=[(c[0], c[1]) for c in _proj_polygon_ll],
            color="#22c55e", fill=True, fill_opacity=0.25, weight=3
        ).add_to(m)
        st_folium(m, width=None, height=340, returned_objects=[])
        st.caption("To edit or clear this boundary, go to Project Setup and redraw it there.")
        st.success(f"📌 {lat:.5f}°N, {lon:.5f}°E")

    elif _has_proj:
        # ── Project context, point/quick mode only — show pinned map ──
        lat = st.session_state.get("map_lat", _proj_lat)
        lon = st.session_state.get("map_lon", _proj_lon)
        center = st.session_state.get("map_center", [lat, lon])
        zoom   = st.session_state.get("map_zoom", 13)

        m = folium.Map(location=center, zoom_start=zoom,
                       tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                       attr="Google Satellite")
        folium.Marker([lat, lon], tooltip="Project site",
                      icon=folium.Icon(color="green", icon="star")).add_to(m)

        st.caption("Location from your project. Click map to override.")
        map_result = st_folium(m, width=None, height=340, returned_objects=["last_clicked"])
        if map_result and map_result.get("last_clicked"):
            _lc = map_result["last_clicked"]
            st.session_state["map_lat"]    = _lc["lat"]
            st.session_state["map_lon"]    = _lc["lng"]
            st.session_state["map_center"] = [_lc["lat"], _lc["lng"]]
            st.session_state["map_zoom"]   = zoom
            lat = _lc["lat"]
            lon = _lc["lng"]
            st.rerun()
        st.success(f"📌 {lat:.5f}°N, {lon:.5f}°E")

    else:
        # ── No project context: full input method selector ──
        method = st.radio("Input method", [
            "🗺️ Click on Map",
            "📐 Coordinates (Lat / Lon)",
            "🔗 Google Maps Link",
            "📁 Upload KML / KMZ File"
        ])

        if method == "🗺️ Click on Map":
            nav1, nav2 = st.tabs(["🔍 Search by Name", "📍 Enter Coordinates"])

            with nav1:
                search_q = st.text_input("Place name", placeholder="e.g. Houston Texas or Rajasthan India",
                                         label_visibility="collapsed")
                if search_q and search_q != st.session_state.get("last_map_search", ""):
                    with st.spinner("Searching…"):
                        slat, slon, _ = geocode_address(search_q)
                    if slat:
                        st.session_state["map_center"]      = [slat, slon]
                        st.session_state["map_zoom"]        = 13
                        st.session_state["last_map_search"] = search_q
                        st.rerun()
                    else:
                        st.session_state["last_map_search"] = search_q
                        st.warning("Location not found — try adding the country name.")

            with nav2:
                _c1, _c2 = st.columns(2)
                with _c1:
                    _lat_in = st.text_input("↕️ Latitude",  placeholder="e.g. 26.8467", key="siq_clat")
                with _c2:
                    _lon_in = st.text_input("↔️ Longitude", placeholder="e.g. 80.9462", key="siq_clon")
                _coord_key = f"{_lat_in}|{_lon_in}"
                if _lat_in and _lon_in and _coord_key != st.session_state.get("siq_last_coord", ""):
                    try:
                        _lf, _lnf = float(_lat_in.strip()), float(_lon_in.strip())
                        if -90 <= _lf <= 90 and -180 <= _lnf <= 180:
                            st.session_state["map_center"]    = [_lf, _lnf]
                            st.session_state["map_zoom"]      = 15
                            st.session_state["map_lat"]       = _lf
                            st.session_state["map_lon"]       = _lnf
                            st.session_state["siq_last_coord"] = _coord_key
                            st.rerun()
                    except ValueError:
                        pass
                _paste = st.text_input("Or paste  lat, lon", placeholder="26.8467, 80.9462",
                                       key="siq_paste")
                if _paste and _paste != st.session_state.get("siq_last_paste", ""):
                    try:
                        _p = _paste.replace(";", ",").split(",")
                        _lf, _lnf = float(_p[0].strip()), float(_p[1].strip())
                        if -90 <= _lf <= 90 and -180 <= _lnf <= 180:
                            st.session_state["map_center"]   = [_lf, _lnf]
                            st.session_state["map_zoom"]     = 15
                            st.session_state["map_lat"]      = _lf
                            st.session_state["map_lon"]      = _lnf
                            st.session_state["siq_last_paste"] = _paste
                            st.rerun()
                    except Exception:
                        pass

            center = st.session_state.get("map_center", [30.0, 10.0])
            zoom   = st.session_state.get("map_zoom", 3)
            m = folium.Map(location=center, zoom_start=zoom,
                           tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                           attr="Google Satellite")
            if "map_lat" in st.session_state:
                folium.Marker(
                    [st.session_state["map_lat"], st.session_state["map_lon"]],
                    tooltip="Selected site",
                    icon=folium.Icon(color="green", icon="star")
                ).add_to(m)

            st.caption("Click anywhere on the map to drop a pin on your site.")
            map_result = st_folium(m, width=None, height=340, returned_objects=["last_clicked"])

            if map_result and map_result.get("last_clicked"):
                _lc = map_result["last_clicked"]
                st.session_state["map_lat"]    = _lc["lat"]
                st.session_state["map_lon"]    = _lc["lng"]
                st.session_state["map_center"] = [_lc["lat"], _lc["lng"]]
                st.session_state["map_zoom"]   = zoom
                st.rerun()

            if "map_lat" in st.session_state:
                lat = st.session_state["map_lat"]
                lon = st.session_state["map_lon"]
                st.success(f"📌 {lat:.5f}°N, {lon:.5f}°E")
            else:
                st.info("Search a location or click the map to pin your site.")

        elif method == "📐 Coordinates (Lat / Lon)":
            lat = st.number_input("↕️ Latitude",  value=48.5665, format="%.5f")
            lon = st.number_input("↔️ Longitude", value=12.1521, format="%.5f")

        elif method == "🔗 Google Maps Link":
            st.caption("Paste a Google Maps URL **or** right-click any point in Google Maps → click the coordinates at the top → paste here.")
            maps_url = st.text_input("Paste Google Maps link or coordinates", placeholder="17.1401, 78.4802  or  https://maps.google.com/...")
            if maps_url:
                lat, lon = parse_google_maps_url(maps_url)
                if lat is not None and lon is not None:
                    st.success(f"📌 Extracted: {lat:.5f}°N, {lon:.5f}°E")
                else:
                    st.warning("Could not extract coordinates — try right-clicking a point in Google Maps and copying the coordinates directly.")

        elif method == "📁 Upload KML / KMZ File":
            st.caption("Export your site boundary from Google Earth, PVcase, or any GIS tool.")
            uploaded = st.file_uploader("Upload site boundary file", type=["kml", "kmz"])
            if uploaded:
                data = uploaded.read()
                if uploaded.name.endswith(".kmz"):
                    lat, lon, kml_area = parse_kmz_bytes(data)
                else:
                    lat, lon, kml_area = parse_kml_bytes(data)
                if lat is not None and lon is not None:
                    st.success(f"📌 Centroid: {lat:.5f}°N, {lon:.5f}°E  |  Area: {kml_area} ha")
                else:
                    st.error("Could not read coordinates from file. Ensure it contains polygon geometry.")

    # ── Site area ─────────────────────────────────────────────────────────────
    _default_area = float(_proj.get("area_ha") or 10.0)
    if kml_area:
        area_ha = st.number_input("Site area (ha) — from file", min_value=0.1, value=float(kml_area), step=0.5)
    else:
        area_ha = st.number_input("Site area (ha)", min_value=0.1, value=_default_area, step=0.5,
                                   help="Adjust for capacity estimate.")

    _used = is_over_limit(_username, "siteiq")
    _left = remaining(_username, "siteiq")

    if is_over_limit(_username, "siteiq"):
        st.markdown(f"""
        <div style="background:#fff;border:1.5px solid #e2ede2;border-radius:14px;
                    padding:1.8rem 1.6rem;text-align:center;margin-top:0.5rem;
                    font-family:'Inter',sans-serif;">
          <div style="font-size:2rem;margin-bottom:0.5rem;">🔒</div>
          <div style="font-size:1.2rem;font-weight:800;color:#1a5c2e;margin-bottom:0.4rem;">
            Free Trial Complete
          </div>
          <div style="color:#555;font-size:0.88rem;margin-bottom:1.2rem;line-height:1.6;">
            You've used all <b>{FREE_LIMIT} free analyses</b> in SiteIQ.<br>
            Upgrade to run unlimited screenings.
          </div>
          <a href="{STRIPE_LINK}" target="_blank"
             style="display:inline-block;background:linear-gradient(135deg,#1d9e52,#145f34);
                    color:#fff;font-weight:700;font-size:0.95rem;padding:0.75rem 2rem;
                    border-radius:9px;text-decoration:none;letter-spacing:0.01em;">
            Upgrade to Professional →
          </a>
          <div style="margin-top:1rem;font-size:0.78rem;color:#999;">
            Questions? <a href="mailto:contact@pvmath.de" style="color:#1d9e52;">contact@pvmath.de</a>
          </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        if _left <= 1:
            st.warning(f"⚠️ {_left} free analysis remaining after this run.")
        go = st.button("🔍 Run Site Screening", type="primary", use_container_width=True)

with right:
    if not is_over_limit(_username, "siteiq") and go:
        if lat is None or lon is None:
            st.error("Please select a site location using one of the input methods on the left.")
            st.stop()

        st.session_state["siteiq_project_name"] = project_name or "Unnamed Project"
        st.session_state["siteiq_country"]      = project_country_input or ""
        st.session_state["siteiq_lat"]          = lat
        st.session_state["siteiq_lon"]          = lon
        st.session_state["siteiq_area_ha"]      = area_ha

        increment_usage(_username, "siteiq")

        with st.spinner("Fetching solar resource data from EU PVGIS…"):
            solar = get_solar_data(lat, lon)
        with st.spinner("Analysing terrain & slope…"):
            _proj_polygon = _proj.get("polygon_coords") if _proj.get("mode") == "full" else None
            terrain = get_terrain_data(lat, lon, polygon=_proj_polygon)

        s_lbl, _, s_detail = assess_slope(terrain["max_slope_pct"] if terrain["success"] else 0, _mount_type)
        if solar["success"]:
            g_lbl, _, g_detail = assess_solar(solar["annual_ghi"])
        else:
            # Don't report a fabricated "0 kWh/m² — Poor" verdict when the PVGIS
            # call itself failed — that reads as a real (and possibly very wrong)
            # site assessment. Surface it as a data error instead.
            g_lbl, g_detail = "⚠️ Data unavailable", "Solar resource data could not be retrieved for this location — try again or check PVGIS coverage."
        country, eeg_status, eeg_note = assess_eeg(lat, lon, _land_use, project_country_input)
        cap_mw, cap_mwh = site_capacity(area_ha, _land_use, _mount_type)
        verdict, verdict_txt = overall_verdict(s_lbl, g_lbl, _land_use, _mount_type)

        badge_color = "#1a5c2e" if _land_use == "Agri-PV" else "#1565c0"
        st.markdown(
            f'<span style="background:{badge_color};color:white;padding:3px 10px;border-radius:4px;font-size:0.8rem;">'
            f'{land_use} · {mount_type}</span>',
            unsafe_allow_html=True
        )
        st.markdown("")

        if "✅" in verdict:
            st.success(f"**{verdict}** — {verdict_txt}")
        elif "⚠️" in verdict:
            st.warning(f"**{verdict}** — {verdict_txt}")
        else:
            st.error(f"**{verdict}** — {verdict_txt}")

        c1, c2, c3, c4 = st.columns(4)
        _metrics = [
            (c1, "fa-sun",            "#f5a623", "Annual GHI",   f"{solar.get('annual_ghi','—')} kWh/m²"),
            (c2, "fa-mountain",       "#5b9bd5", "Max Slope",    f"{terrain.get('max_slope_pct','—')}%"),
            (c3, "fa-bolt",           "#2ecc71", "Est. Capacity",f"{cap_mw} MWp"),
            (c4, "fa-ruler-combined", "#a87fd4", "Optimal Tilt", f"{solar.get('optimal_tilt','—')}°"),
        ]
        for _mc, _icon, _ic, _lbl, _val in _metrics:
            _mc.markdown(
                f'<div class="metric-card">'
                f'<div class="mc-icon"><i class="fa-solid {_icon}" style="color:{_ic};"></i></div>'
                f'<div class="mc-label">{_lbl}</div>'
                f'<div class="mc-value">{_val}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

        if _proj.get("mode") == "full" and _proj.get("polygon_coords"):
            st.caption(
                "⚡ Capacity estimated from your drawn site boundary area — "
                f"**{area_ha} ha**."
            )
        else:
            st.caption(
                f"⚡ Capacity estimated from a manually entered area (**{area_ha} ha**), "
                "not a drawn boundary — treat this as a rough figure. Draw a site "
                "boundary in Project Setup (Full Mode) for a boundary-derived capacity estimate."
            )

        if terrain.get("success"):
            if terrain.get("boundary_sampled"):
                st.caption(
                    f"📐 Slope assessed from {terrain.get('sample_points','—')} sample points across your drawn "
                    f"site boundary — {terrain.get('pct_over5','—')}% of points >5% slope, "
                    f"{terrain.get('pct_over10','—')}% >10%. Run TopoIQ for full-resolution, area-weighted terrain stats."
                )
            else:
                st.caption(
                    f"📍 Slope estimated from {terrain.get('sample_points','—')} elevation samples within a 500m "
                    "radius of the pin. Draw a site boundary in Project Setup for boundary-based sampling, or run "
                    "TopoIQ for full-resolution terrain analysis."
                )

        st.divider()

        d1, d2 = st.columns(2)
        with d1:
            st.markdown('<div class="section-hdr"><i class="fa-solid fa-sun" style="color:#f5a623;"></i> Solar Resource</div>', unsafe_allow_html=True)
            (st.success if "✅" in g_lbl else st.warning if "⚠️" in g_lbl else st.error)(g_detail)

            st.markdown('<div class="section-hdr" style="margin-top:0.8rem;"><i class="fa-solid fa-scale-balanced" style="color:#a87fd4;"></i> Regulatory</div>', unsafe_allow_html=True)
            st.info(f"{country}  \n{eeg_status}  \n_{eeg_note}_")

        with d2:
            st.markdown('<div class="section-hdr"><i class="fa-solid fa-mountain" style="color:#5b9bd5;"></i> Terrain & Slope</div>', unsafe_allow_html=True)
            (st.success if "✅" in s_lbl else st.warning if "⚠️" in s_lbl else st.error)(s_detail)

            st.markdown('<div class="section-hdr" style="margin-top:0.8rem;"><i class="fa-solid fa-water" style="color:#4ab0d4;"></i> Flood Risk</div>', unsafe_allow_html=True)
            flood_risk, flood_detail, flood_portal, flood_portal_name = get_flood_risk(
                lat, lon, terrain.get("center_elev") if terrain["success"] else None
            )
            if "🔴" in flood_risk:
                st.error(f"**{flood_risk}**  \n{flood_detail}  \n[Check {flood_portal_name} ↗]({flood_portal})")
            elif "🟠" in flood_risk or "🟡" in flood_risk:
                st.warning(f"**{flood_risk}**  \n{flood_detail}  \n[Check {flood_portal_name} ↗]({flood_portal})")
            else:
                st.success(f"**{flood_risk}**  \n{flood_detail}  \n[Verify at {flood_portal_name} ↗]({flood_portal})")

        st.divider()
        with st.expander("Rating Scale — what do the colours mean?"):
            st.markdown("""
| Rating | Meaning | Action |
|--------|---------|--------|
| ✅ Excellent / Good | Parameter is within ideal range | Proceed — no major concerns |
| ⚠️ Acceptable | Feasible but has constraints | Proceed with attention to this factor |
| ⚠️ Challenging | Near the limit — significant effort needed | Detailed study mandatory |
| ❌ Critical | Exceeds viable threshold | High risk — reconsider site or system type |
| 🟢 Low flood risk | Elevated terrain, flood exposure likely low | Verify at local portal |
| 🟡 Low-Moderate risk | Moderate terrain, check watercourse proximity | Cross-check official flood maps |
| 🟠 Moderate risk | Low-lying terrain, flood exposure possible | Manual flood check required |
| 🔴 High flood risk | Very low elevation, high flood exposure | Official flood zone study required |
""")

        if solar["success"] and solar.get("monthly"):
            st.divider()
            st.markdown('<div class="section-hdr"><i class="fa-solid fa-chart-bar" style="color:#f5a623;"></i> Monthly Solar Irradiation (kWh/m²)</div>', unsafe_allow_html=True)
            st.bar_chart(pd.DataFrame(solar["monthly"]).set_index("Month"))

        st.divider()
        pdf = build_pdf(
            site_name=project_name or f"Project_{lat:.3f}_{lon:.3f}",
            lat=lat, lon=lon, area_ha=area_ha,
            solar=solar, terrain=terrain,
            country=country, eeg_status=eeg_status, eeg_note=eeg_note,
            slope_lbl=s_lbl, solar_lbl=g_lbl,
            verdict=verdict, verdict_txt=verdict_txt,
            cap_mw=cap_mw, cap_mwh=cap_mwh,
            land_use=_land_use, mount_type=_mount_type,
            project_country=project_country_input
        )
        st.download_button(
            label="⬇️  Download PDF Report",
            data=pdf,
            file_name=f"SiteIQ_{(project_name or 'report').replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True
        )

    else:
        st.caption("Enter a site location on the left and click **Run Site Screening** to get:")
        wc1, wc2 = st.columns(2)
        _cards = [
            (wc1, "#1a3a2a", "#0f2a1e", "#2a6040", "#4caf82",
             "SOLAR RESOURCE", "Annual GHI · Monthly irradiation · Optimal tilt angle"),
            (wc2, "#1a2a3a", "#0f1e2a", "#2a4060", "#5b9bd5",
             "TERRAIN & SLOPE", "Max slope % · Centre elevation · Tracker suitability"),
            (wc1, "#2a1a3a", "#1e0f2a", "#5a3a80", "#a87fd4",
             "REGULATORY CHECK", "Country-specific incentives · Grid authority · Permitting contacts"),
            (wc2, "#1a2a3a", "#0a1828", "#1a4a6a", "#4ab0d4",
             "FLOOD RISK", "Elevation-based assessment · Local flood portal links"),
            (wc1, "#2a2a1a", "#1e1e0f", "#5a5a20", "#d4c44a",
             "CAPACITY ESTIMATE", "MWp & annual MWh · Density by system type"),
            (wc2, "#2a1a1a", "#1e0f0f", "#6a2a2a", "#d47a4a",
             "PDF REPORT", "One-click download · Professional format · Client-ready"),
        ]
        for _col, _bg1, _bg2, _bd, _tc, _title, _desc in _cards:
            _col.markdown(
                f'<div style="background:linear-gradient(135deg,{_bg1},{_bg2});'
                f'border:1px solid {_bd};border-radius:10px;padding:1rem;margin-bottom:0.75rem;">'
                f'<div style="color:{_tc};font-weight:700;font-size:0.9rem;">{_title}</div>'
                f'<div style="color:#ccc;font-size:0.78rem;margin-top:0.3rem;">{_desc}</div>'
                f'</div>',
                unsafe_allow_html=True
            )
        st.caption("Data: PVGIS JRC · EU-DEM / SRTM via OpenTopoData · OpenStreetMap  |  SiteIQ by PVMath — Module 1 of 3 · pvmath.com")
