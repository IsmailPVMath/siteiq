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
    increment_usage, is_over_limit, remaining, FREE_LIMIT, STRIPE_LINK, PRICE_LABEL
)
from streamlit_folium import st_folium
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.units import cm

# ── User ID ──
_username = st.session_state.get("pvm_user_id", "guest")

# ─── Styling ──────────────────────────────────────────────────────────────────
st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=DM+Serif+Display&display=swap" rel="stylesheet">
<style>
    html, body, [class*="css"] {
        font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif !important;
        font-size: 16px !important;
    }
    /* ── Global font size lift ── */
    [data-testid="stMarkdown"] p,
    [data-testid="stMarkdown"] li,
    [data-testid="stMarkdown"] span  { font-size: 1rem !important; line-height: 1.7 !important; }
    [data-testid="stRadio"] label span  { font-size: 1rem !important; }
    [data-testid="stCheckbox"] label span { font-size: 1rem !important; }
    [data-testid="stSelectbox"] label,
    [data-testid="stTextInput"] label,
    [data-testid="stNumberInput"] label,
    [data-testid="stFileUploader"] label { font-size: 0.97rem !important; font-weight: 600 !important; color: #2a3a2a !important; }
    [data-testid="stSelectbox"] div[data-baseweb="select"] span,
    [data-testid="stTextInput"] input   { font-size: 0.97rem !important; }
    [data-testid="stMetric"] label      { font-size: 0.78rem !important; font-weight: 600 !important; text-transform: uppercase !important; letter-spacing: 0.05em !important; color: #666 !important; }
    [data-testid="stMetricValue"]       { font-size: 1.6rem !important; font-weight: 700 !important; }
    [data-testid="stExpander"] summary p { font-size: 0.97rem !important; font-weight: 600 !important; }
    [data-testid="stAlert"] p           { font-size: 0.97rem !important; }
    button[data-testid="stBaseButton-secondary"],
    button[data-testid="stBaseButton-primary"] { font-size: 0.97rem !important; }
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
    .pvmath-app-name { font-size: 1.75rem; font-weight: 800; letter-spacing: -0.02em; color: #1a5c2e; }
    .pvmath-app-sub  { font-size: 0.88rem; color: #888; font-weight: 500; }
    .pvmath-tagline  { font-size: 0.95rem; color: #5a7a5a; margin-top: 0.15rem; font-weight: 400; line-height: 1.5; }

    /* ── Section headers ── */
    .section-hdr {
        font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.13em; color: #1d9e52;
        display: flex; align-items: center; gap: 0.5rem;
        margin: 1.4rem 0 0.75rem 0; padding-bottom: 0.45rem;
        border-bottom: 2px solid #e2ede2;
    }
    /* ── Result value text ── */
    .result-label { font-size: 0.82rem; color: #666; font-weight: 500; text-transform: uppercase; letter-spacing: 0.06em; }
    .result-value { font-size: 1.35rem; font-weight: 700; color: #1a2e1a; line-height: 1.2; }
    .result-unit  { font-size: 0.85rem; font-weight: 400; color: #888; margin-left: 0.15rem; }

    /* ── Metric cards ── */
    div[data-testid="metric-container"] {
        background: #fff; border: 1px solid #e2ede2;
        border-radius: 10px; padding: 1rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.04);
    }

    /* ── Buttons ── */
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

    /* ── Tabs ── */
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        color: #1d9e52 !important; border-bottom-color: #1d9e52 !important; font-weight: 700 !important;
    }
    div[data-testid="stTabs"] button[role="tab"] { font-weight: 500 !important; }

    /* ── Download button ── */
    div[data-testid="stDownloadButton"] > button {
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important; border-radius: 8px !important;
    }

    /* ── Inputs ── */
    div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea {
        font-family: 'Inter', sans-serif !important;
        border-radius: 8px !important;
    }

    /* ── Alert boxes ── */
    div[data-testid="stAlert"] {
        border-radius: 10px !important; font-weight: 500;
    }

    /* ── Expander ── */
    div[data-testid="stExpander"] {
        border: 1px solid #e2ede2 !important; border-radius: 10px !important;
    }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] { background: #f5f7f5 !important; }
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


def get_solar_data(lat, lon):
    try:
        r = requests.get(
            "https://re.jrc.ec.europa.eu/api/v5_2/PVcalc",
            params={
                "lat": lat, "lon": lon,
                "peakpower": 1, "loss": 14,
                "outputformat": "json",
                "mountingplace": "free",
                "optimalangles": 1,
            },
            timeout=20
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
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_terrain_data(lat, lon, radius_km=0.5):
    delta = radius_km / 111.0
    points = [
        (lat,         lon),
        (lat + delta, lon),
        (lat - delta, lon),
        (lat,         lon + delta),
        (lat,         lon - delta),
    ]
    locations = "|".join(f"{p[0]},{p[1]}" for p in points)
    in_europe = 34 <= lat <= 72 and -25 <= lon <= 45
    dataset   = "eudem25m" if in_europe else "srtm30m"
    try:
        r = requests.get(
            f"https://api.opentopodata.org/v1/{dataset}",
            params={"locations": locations},
            timeout=15
        )
        results = r.json().get("results", [])
        elevs = [res["elevation"] for res in results if res.get("elevation") is not None]
        if len(elevs) >= 5:
            ns = abs(elevs[1] - elevs[2]) / (2 * radius_km * 1000) * 100
            ew = abs(elevs[3] - elevs[4]) / (2 * radius_km * 1000) * 100
            return {
                "success":         True,
                "center_elev":     round(elevs[0], 1),
                "max_slope_pct":   round(max(ns, ew), 1),
                "elevation_range": round(max(elevs) - min(elevs), 1),
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
    in_au = any(x in c for x in ["australia","australian"])
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
        return "❌ NOT RECOMMENDED",        "One or more critical issues identified. High risk to project viability."
    elif yellows >= 2:
        return "⚠️ PROCEED WITH CAUTION",   "Multiple moderate concerns. Detailed study recommended before committing."
    elif yellows == 1:
        return "⚠️ CONDITIONAL GO",         f"Site shows promise but has considerations to address in detailed {label} design."
    else:
        return "✅ RECOMMENDED FOR STUDY",  f"Strong {label} potential. Proceed to detailed feasibility study."


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
    GREEN  = colors.HexColor("#1a5c2e")
    LGRAY  = colors.HexColor("#f8f9fa")
    story  = []

    C_GREEN  = colors.HexColor("#1a5c2e")
    C_LGREEN = colors.HexColor("#e8f5e9")
    C_YELLOW = colors.HexColor("#f9a825")
    C_LYELLOW= colors.HexColor("#fff9e6")
    C_ORANGE = colors.HexColor("#e65100")
    C_LORANG = colors.HexColor("#fff3e0")
    C_RED    = colors.HexColor("#c62828")
    C_LRED   = colors.HexColor("#ffebee")

    def lp(text, color=colors.black, bold=False, size=8):
        fn = "Helvetica-Bold" if bold else "Helvetica"
        return Paragraph(text, ParagraphStyle("lp", parent=styles["Normal"],
                         fontSize=size, fontName=fn, textColor=color,
                         leading=10, spaceAfter=0))

    story.append(Paragraph("SiteIQ by PVMath",
        ParagraphStyle("T", parent=styles["Heading1"], fontSize=22, textColor=GREEN, spaceAfter=4)))
    story.append(Paragraph("Site Screening Report",
        ParagraphStyle("S", parent=styles["Normal"], fontSize=11, textColor=colors.grey)))
    story.append(HRFlowable(width="100%", thickness=2, color=GREEN))
    story.append(Spacer(1, 0.4*cm))

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

    v_color = GREEN if "✅" in verdict else \
              colors.HexColor("#f9a825") if "⚠️" in verdict else \
              colors.HexColor("#d32f2f")
    story.append(Paragraph("OVERALL VERDICT",
        ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, textColor=GREEN)))
    vt = Table([[
        Paragraph(f"<b>{verdict}</b>",
            ParagraphStyle("V", parent=styles["Normal"], fontSize=12, textColor=v_color)),
        Paragraph(verdict_txt, styles["Normal"])
    ]], colWidths=[6*cm, 11*cm])
    vt.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1), LGRAY),
        ("GRID",      (0,0),(-1,-1), 0.5, colors.lightgrey),
        ("TOPPADDING",(0,0),(-1,-1), 10),
        ("BOTTOMPADDING",(0,0),(-1,-1), 10),
        ("LEFTPADDING",(0,0),(-1,-1), 10),
    ]))
    story.append(vt)
    story.append(Spacer(1, 0.5*cm))

    story.append(Paragraph("KEY METRICS",
        ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, textColor=GREEN)))
    rows = [
        ["Metric", "Value", "Rating"],
        ["Annual GHI",         f"{solar.get('annual_ghi','—')} kWh/m²/yr",   solar_lbl.split("—")[0].strip()],
        ["Annual Yield",       f"{solar.get('annual_yield','—')} kWh/kWp/yr","—"],
        ["Optimal Tilt",       f"{solar.get('optimal_tilt','—')}°",           "—"],
        ["Max Terrain Slope",  f"{terrain.get('max_slope_pct','—')}%",        slope_lbl.split("—")[0].strip()],
        ["Elevation (centre)", f"{terrain.get('center_elev','—')} m asl",     "—"],
        ["Est. Capacity",      f"{cap_mw} MWp",                               f"Density basis: {0.18 if land_use=='Agri-PV' and mount_type=='Single-Axis Tracker' else 0.20 if land_use=='Agri-PV' else 0.35 if mount_type=='Single-Axis Tracker' else 0.40} MW/ha"],
        ["Est. Annual Output", f"{cap_mwh:,.0f} MWh/yr",                      "Indicative only"],
        ["EEG Status",         eeg_status,                                    eeg_note],
    ]
    mt = Table(rows, colWidths=[6*cm, 6*cm, 5*cm])
    mt.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,0), GREEN),
        ("TEXTCOLOR",    (0,0),(-1,0), colors.white),
        ("FONTNAME",     (0,0),(-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0),(-1,-1), 9),
        ("GRID",         (0,0),(-1,-1), 0.5, colors.lightgrey),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, LGRAY]),
        ("TOPPADDING",   (0,0),(-1,-1), 5),
        ("BOTTOMPADDING",(0,0),(-1,-1), 5),
    ]))
    story.append(mt)
    story.append(Spacer(1, 0.5*cm))

    # ── Monthly Irradiation Table ─────────────────────────────────────────────
    monthly_data = solar.get("monthly", [])
    if monthly_data:
        story.append(Paragraph("MONTHLY SOLAR IRRADIATION (kWh/m²)",
            ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, textColor=GREEN)))

        months_abbr = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        ghi_vals = [row.get("GHI (kWh/m²)", 0) for row in monthly_data[:12]]
        max_ghi  = max(ghi_vals) if ghi_vals else 1

        # Header row
        hdr = [lp(m, colors.white, bold=True, size=8) for m in months_abbr]
        # Value row with background intensity scaled to value
        def ghi_bg(val):
            ratio = val / max_ghi if max_ghi else 0
            r = int(232 - ratio * (232 - 26))
            g = int(245 - ratio * (245 - 92))
            b = int(238 - ratio * (238 - 46))
            return colors.Color(r/255, g/255, b/255)

        val_cells = [lp(f"{v:.0f}", colors.HexColor("#1a2e1a"), bold=True, size=9) for v in ghi_vals]
        col_w = [1.42*cm] * 12
        monthly_tbl = Table([hdr, val_cells], colWidths=col_w)
        bg_cmds = [("BACKGROUND", (i,0), (i,0), GREEN) for i in range(12)]
        bg_cmds += [("BACKGROUND", (i,1), (i,1), ghi_bg(ghi_vals[i])) for i in range(12)]
        monthly_tbl.setStyle(TableStyle([
            ("GRID",         (0,0),(-1,-1), 0.5, colors.lightgrey),
            ("ALIGN",        (0,0),(-1,-1), "CENTER"),
            ("TOPPADDING",   (0,0),(-1,-1), 5),
            ("BOTTOMPADDING",(0,0),(-1,-1), 5),
        ] + bg_cmds))
        story.append(monthly_tbl)
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph(
            f"Peak month: {months_abbr[ghi_vals.index(max_ghi)]} ({max_ghi:.0f} kWh/m²)  |  "
            f"Annual total: {sum(ghi_vals):.0f} kWh/m²",
            ParagraphStyle("sub", parent=styles["Normal"], fontSize=8, textColor=colors.grey)
        ))
        story.append(Spacer(1, 0.5*cm))

    story.append(Paragraph("RATING SCALE",
        ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, textColor=GREEN)))

    legend_rows = [
        [lp("Rating", colors.white, bold=True), lp("Meaning", colors.white, bold=True), lp("Action", colors.white, bold=True)],
        [lp("EXCELLENT / GOOD", C_GREEN,  bold=True), lp("Parameter is within ideal range for this project type"),    lp("Proceed — no major concerns")],
        [lp("ACCEPTABLE",       C_YELLOW, bold=True), lp("Feasible range but with constraints"),                      lp("Proceed — monitor this factor")],
        [lp("CHALLENGING",      C_ORANGE, bold=True), lp("Near the feasibility limit — significant effort required"), lp("Detailed study mandatory before commitment")],
        [lp("CRITICAL",         C_RED,    bold=True), lp("Exceeds viable threshold for this system type"),            lp("High risk — reconsider site or system")],
        [lp("LOW FLOOD RISK",   C_GREEN,  bold=True), lp("Elevated terrain — flood exposure likely low"),             lp("Verify at local flood portal")],
        [lp("LOW-MOD FLOOD",    C_YELLOW, bold=True), lp("Moderate terrain — watercourse proximity check needed"),    lp("Cross-check official flood maps")],
        [lp("MODERATE FLOOD",   C_ORANGE, bold=True), lp("Low-lying terrain — flood exposure possible"),              lp("Manual flood risk check required")],
        [lp("HIGH FLOOD RISK",  C_RED,    bold=True), lp("Very low elevation — high flood exposure likely"),          lp("Flood zone study required before proceeding")],
    ]
    lt = Table(legend_rows, colWidths=[4*cm, 8.5*cm, 4.5*cm])
    lt.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  GREEN),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.lightgrey),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 4),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, LGRAY]),
        ("BACKGROUND", (0,1), (0,1), C_LGREEN),
        ("BACKGROUND", (0,2), (0,2), C_LYELLOW),
        ("BACKGROUND", (0,3), (0,3), C_LYELLOW),
        ("BACKGROUND", (0,4), (0,4), C_LRED),
        ("BACKGROUND", (0,5), (0,5), C_LGREEN),
        ("BACKGROUND", (0,6), (0,6), C_LYELLOW),
        ("BACKGROUND", (0,7), (0,7), C_LORANG),
        ("BACKGROUND", (0,8), (0,8), C_LRED),
    ]))
    story.append(lt)
    story.append(Spacer(1, 0.5*cm))

    story.append(Paragraph("RECOMMENDED NEXT STEPS",
        ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, textColor=GREEN)))
    for step in get_next_steps(project_country or country, land_use):
        story.append(Paragraph(step, styles["Normal"]))
        story.append(Spacer(1, 0.2*cm))

    story.append(Spacer(1, 0.4*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        "Generated by SiteIQ — Solar Site Intelligence Platform by PVMath | For professional use only. "
        "Data sources: PVGIS JRC (EU Commission), EU-DEM / SRTM via OpenTopoData, OpenStreetMap (Nominatim).",
        ParagraphStyle("Ft", parent=styles["Normal"], fontSize=7, textColor=colors.grey)
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
_has_proj   = bool(_proj_lat and _proj_lon)

if _has_proj:
    st.markdown(f"""
    <div style="background:#e8f5ee;border:1px solid #b8ddc8;border-radius:8px;
                padding:0.65rem 1rem;margin-bottom:0.9rem;font-size:0.89rem;color:#1a3a1a;">
      <strong>📋 Project:</strong>&nbsp; {_proj_name}
      &nbsp;·&nbsp; {_proj_ctry}
      &nbsp;·&nbsp; {_proj_lat:.5f}°N, {_proj_lon:.5f}°E
    </div>
    """, unsafe_allow_html=True)
    # Pre-centre the map on the project location (only if no map interaction yet)
    if "map_center" not in st.session_state:
        st.session_state["map_center"] = [_proj_lat, _proj_lon]
        st.session_state["map_zoom"]   = 13

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
        st.success("✅ Agri-PV dual-use · Local agricultural regulations apply")
    else:
        st.info("ℹ️ Standard ground-mount · No dual-use requirements")

with pt_col2:
    mount_type = st.radio(
        "**Mounting System**",
        ["Fixed Tilt", "Single-Axis Tracker"],
        help="Tracker systems require flatter terrain and more N-S row spacing."
    )
    if mount_type == "Single-Axis Tracker":
        st.warning("⚠️ Tracker: max recommended slope ± 8° · Higher CAPEX, higher yield")
    else:
        st.info("ℹ️ Fixed Tilt: max recommended slope ≤ 10% · Lower CAPEX")

_land_use   = "Agri-PV" if "Agri-PV" in land_use else "Standard"
_mount_type = mount_type

st.divider()

left, right = st.columns([1, 2])

with left:
    st.subheader("📍 Site Location")
    method = st.radio("Input method", [
        "🗺️ Click on Map",
        "📐 Coordinates (Lat / Lon)",
        "🔗 Google Maps Link",
        "📁 Upload KML / KMZ File"
    ])

    lat = lon = None
    kml_area = None

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
                _lat_in = st.text_input("Latitude",  placeholder="e.g. 26.8467", key="siq_clat")
            with _c2:
                _lon_in = st.text_input("Longitude", placeholder="e.g. 80.9462", key="siq_clon")
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
        lat = st.number_input("Latitude",  value=48.5665, format="%.5f")
        lon = st.number_input("Longitude", value=12.1521, format="%.5f")

    elif method == "🔗 Google Maps Link":
        st.caption("Paste a Google Maps URL **or** right-click any point in Google Maps → click the coordinates at the top → paste here.")
        maps_url = st.text_input("Paste Google Maps link or coordinates", placeholder="17.1401, 78.4802  or  https://maps.google.com/...")
        if maps_url:
            lat, lon = parse_google_maps_url(maps_url)
            if lat and lon:
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
            if lat and lon:
                st.success(f"📌 Centroid: {lat:.5f}°N, {lon:.5f}°E  |  Area: {kml_area} ha")
            else:
                st.error("Could not read coordinates from file. Ensure it contains polygon geometry.")

    if kml_area:
        area_ha = st.number_input("Site area (ha) — from file", min_value=0.1, value=float(kml_area), step=0.5)
    else:
        area_ha = st.number_input("Site area (ha)", min_value=0.1, value=10.0, step=0.5,
                                   help="Default 10 ha. Adjust for capacity estimate.")

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
            Upgrade — {PRICE_LABEL} →
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
            terrain = get_terrain_data(lat, lon)

        s_lbl, _, s_detail = assess_slope(terrain["max_slope_pct"] if terrain["success"] else 0, _mount_type)
        g_lbl, _, g_detail = assess_solar(solar["annual_ghi"]       if solar["success"]   else 0)
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
