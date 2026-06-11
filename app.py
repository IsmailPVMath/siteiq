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
from streamlit_folium import st_folium
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.units import cm

# ─── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SiteIQ – Agri-PV Screening",
    page_icon="🌱",
    layout="wide"
)

# ─── Styling ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #1a5c2e; }
    .sub-header  { font-size: 1rem; color: #666; margin-bottom: 1.5rem; }
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div style="display:flex; align-items:center; gap:0.6rem;">
  <span style="font-size:2.2rem;">🌱</span>
  <span class="main-header" style="margin:0;">SiteIQ</span>
  <span style="font-size:0.85rem; color:#888; margin-left:0.5rem; align-self:flex-end; padding-bottom:0.4rem;">by PVMath</span>
</div>
""", unsafe_allow_html=True)
st.markdown('<p class="sub-header">Solar & Agri-PV Site Intelligence Platform</p>', unsafe_allow_html=True)
st.divider()

# ─── Helper Functions ─────────────────────────────────────────────────────────

def geocode_address(address):
    """Convert address to lat/lon via Nominatim (OpenStreetMap)."""
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1},
            headers={"User-Agent": "SolarScout/1.0"},
            timeout=10
        )
        data = r.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"]), data[0]["display_name"]
    except Exception:
        pass
    return None, None, None


def parse_google_maps_url(url):
    """Extract lat/lon from a Google Maps URL."""
    patterns = [
        r'@(-?\d+\.?\d+),(-?\d+\.?\d+)',
        r'q=(-?\d+\.?\d+),(-?\d+\.?\d+)',
        r'll=(-?\d+\.?\d+),(-?\d+\.?\d+)',
        r'place/[^/]+/@(-?\d+\.?\d+),(-?\d+\.?\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return float(match.group(1)), float(match.group(2))
    return None, None


def polygon_area_ha(coords):
    """Shoelace formula — returns area in hectares given list of (lat, lon)."""
    if len(coords) < 3:
        return 0.0
    # Convert to approximate metres using mean lat
    mean_lat = sum(c[0] for c in coords) / len(coords)
    lat_m  = 111320.0
    lon_m  = 111320.0 * math.cos(math.radians(mean_lat))
    pts = [(c[1] * lon_m, c[0] * lat_m) for c in coords]
    n = len(pts)
    area = abs(sum(pts[i][0] * pts[(i+1) % n][1] -
                   pts[(i+1) % n][0] * pts[i][1] for i in range(n))) / 2.0
    return round(area / 10000, 2)  # m² → ha


def parse_kml_bytes(data: bytes):
    """Parse KML bytes → (center_lat, center_lon, area_ha)."""
    try:
        root = ET.fromstring(data)
        ns = {'k': 'http://www.opengis.net/kml/2.2'}
        # Try with namespace first, then without
        coords_el = root.find('.//{http://www.opengis.net/kml/2.2}coordinates')
        if coords_el is None:
            coords_el = root.find('.//coordinates')
        if coords_el is None:
            return None, None, None
        coords = []
        for token in coords_el.text.strip().split():
            parts = token.split(',')
            if len(parts) >= 2:
                coords.append((float(parts[1]), float(parts[0])))  # (lat, lon)
        if not coords:
            return None, None, None
        clat = sum(c[0] for c in coords) / len(coords)
        clon = sum(c[1] for c in coords) / len(coords)
        area = polygon_area_ha(coords)
        return clat, clon, area
    except Exception:
        return None, None, None


def parse_kmz_bytes(data: bytes):
    """Unzip KMZ and parse the inner KML."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            kml_name = next((n for n in z.namelist() if n.endswith('.kml')), None)
            if kml_name:
                return parse_kml_bytes(z.read(kml_name))
    except Exception:
        pass
    return None, None, None


def get_flood_risk(lat, lon, elevation):
    """Estimate flood risk using elevation + country-specific portal links."""
    # Country detection
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

    # Elevation-based preliminary risk
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
    """Fetch annual & monthly solar data from EU PVGIS API."""
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
        tilt    = data["inputs"]["mounting_system"]["fixed"]["slope"].get("optimal", "—")

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
    """Sample 5 elevation points to estimate terrain slope."""
    delta = radius_km / 111.0
    points = [
        (lat,         lon),
        (lat + delta, lon),
        (lat - delta, lon),
        (lat,         lon + delta),
        (lat,         lon - delta),
    ]
    locations = "|".join(f"{p[0]},{p[1]}" for p in points)
    try:
        r = requests.get(
            "https://api.opentopodata.org/v1/eudem25m",
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
    """Slope limits differ: trackers need flatter terrain than fixed tilt."""
    if mount_type == "Single-Axis Tracker":
        if pct <= 3:
            return "✅ Excellent", "green",  f"{pct}% — Ideal for single-axis tracker"
        elif pct <= 6:
            return "⚠️ Acceptable", "yellow", f"{pct}% — Feasible for tracker; grading may be needed"
        elif pct <= 10:
            return "⚠️ Challenging", "yellow", f"{pct}% — Steep for trackers; significant grading required"
        else:
            return "❌ Critical", "red",    f"{pct}% — Too steep for single-axis tracker systems"
    else:  # Fixed Tilt
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


def assess_eeg(lat, lon, land_use="Standard"):
    in_de = 47.3 <= lat <= 55.1 and  5.9 <= lon <= 15.1
    in_at = 46.4 <= lat <= 49.0 and  9.5 <= lon <= 17.2
    in_ch = 45.8 <= lat <= 47.8 and  5.9 <= lon <= 10.5
    if land_use == "Agri-PV":
        if in_de:
            return "🇩🇪 Germany",     "✅ EEG 2023 Agri-PV bonus likely applicable", "Verify agricultural land class (§37 EEG 2023) + DIN SPEC 91434"
        elif in_at:
            return "🇦🇹 Austria",     "⚠️ Check OeMAG Agri-PV provisions",          "Austrian Renewable Energy Expansion Act (EAG)"
        elif in_ch:
            return "🇨🇭 Switzerland", "⚠️ Check KEV/Pronovo Agri-PV rules",          "Swiss Energy Act + cantonal agricultural provisions"
        else:
            return "🌍 Outside DACH", "ℹ️ Check local Agri-PV regulations",          "No EEG — verify local dual-use land rules"
    else:  # Standard
        if in_de:
            return "🇩🇪 Germany",     "✅ EEG 2023 standard Freifläche applicable",  "Eligible for EEG feed-in tariff (§38 EEG 2023)"
        elif in_at:
            return "🇦🇹 Austria",     "⚠️ Check OeMAG Freifläche provisions",        "Austrian Renewable Energy Expansion Act (EAG)"
        elif in_ch:
            return "🇨🇭 Switzerland", "⚠️ Check KEV/Pronovo Freifläche rules",       "Swiss Energy Act (EnG) provisions apply"
        else:
            return "🌍 Outside DACH", "ℹ️ Check local feed-in regulations",           "No EEG — verify local PV incentive scheme"


def site_capacity(area_ha, land_use="Standard", mount_type="Fixed Tilt"):
    """Capacity density varies by system type.
    Standard Fixed Tilt: ~0.40 MW/ha
    Standard Tracker:    ~0.35 MW/ha (more N-S row spacing)
    Agri-PV Fixed Tilt:  ~0.20 MW/ha (elevated, wide spacing for crops)
    Agri-PV Tracker:     ~0.18 MW/ha (elevated tracker + crop clearance)
    """
    if land_use == "Agri-PV":
        density = 0.18 if mount_type == "Single-Axis Tracker" else 0.20
    else:
        density = 0.35 if mount_type == "Single-Axis Tracker" else 0.40
    mw  = round(area_ha * density, 2)
    mwh = round(mw * 1000, 0)
    return mw, mwh


def overall_verdict(slope_lbl, solar_lbl):
    reds    = sum(1 for l in [slope_lbl, solar_lbl] if "❌" in l)
    yellows = sum(1 for l in [slope_lbl, solar_lbl] if "⚠️" in l)
    if reds >= 1:
        return "❌ NOT RECOMMENDED",        "One or more critical issues identified. High risk to project viability."
    elif yellows >= 2:
        return "⚠️ PROCEED WITH CAUTION",   "Multiple moderate concerns. Detailed study recommended before committing."
    elif yellows == 1:
        return "⚠️ CONDITIONAL GO",         "Site shows promise but has considerations to address in detailed design."
    else:
        return "✅ RECOMMENDED FOR STUDY",  "Strong Agri-PV potential. Proceed to detailed feasibility study."


def build_pdf(site_name, lat, lon, area_ha, solar, terrain,
              country, eeg_status, eeg_note,
              slope_lbl, solar_lbl, verdict, verdict_txt,
              cap_mw, cap_mwh,
              land_use="Standard", mount_type="Fixed Tilt"):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm,  bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    GREEN  = colors.HexColor("#1a5c2e")
    LGRAY  = colors.HexColor("#f8f9fa")
    story  = []

    # Header
    story.append(Paragraph("🌱 SiteIQ by PVMath",
        ParagraphStyle("T", parent=styles["Heading1"], fontSize=22, textColor=GREEN, spaceAfter=4)))
    story.append(Paragraph("Agri-PV Site Screening Report",
        ParagraphStyle("S", parent=styles["Normal"], fontSize=11, textColor=colors.grey)))
    story.append(HRFlowable(width="100%", thickness=2, color=GREEN))
    story.append(Spacer(1, 0.4*cm))

    # Site info
    site_rows = [
        ["Site Name",      site_name or "—"],
        ["Coordinates",    f"{lat:.5f}°N, {lon:.5f}°E"],
        ["Site Area",      f"{area_ha} ha"],
        ["Country",        country],
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

    # Verdict
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

    # Metrics table
    story.append(Paragraph("KEY METRICS",
        ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, textColor=GREEN)))
    rows = [
        ["Metric", "Value", "Rating"],
        ["Annual GHI",         f"{solar.get('annual_ghi','—')} kWh/m²/yr",   solar_lbl.split("—")[0].strip()],
        ["Annual Yield",       f"{solar.get('annual_yield','—')} kWh/kWp/yr","—"],
        ["Optimal Tilt",       f"{solar.get('optimal_tilt','—')}°",           "—"],
        ["Max Terrain Slope",  f"{terrain.get('max_slope_pct','—')}%",        slope_lbl.split("—")[0].strip()],
        ["Elevation (centre)", f"{terrain.get('center_elev','—')} m asl",     "—"],
        ["Est. Capacity",      f"{cap_mw} MWp",                               "~0.35 MW/ha Agri-PV density"],
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

    # Next steps
    story.append(Paragraph("RECOMMENDED NEXT STEPS",
        ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, textColor=GREEN)))
    for step in [
        "1. Verify agricultural land classification with local Katasteramt",
        "2. Manual flood risk check: www.hochwasserportal.de",
        "3. Assess grid connection capacity with local DSO",
        "4. Commission agronomic study for DIN SPEC 91434 compliance",
        "5. Pre-consultation with local Bauamt / planning authority",
    ]:
        story.append(Paragraph(step, styles["Normal"]))
        story.append(Spacer(1, 0.2*cm))

    story.append(Spacer(1, 0.4*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        "Generated by SiteIQ — Agri-PV Intelligence Platform by PVMath | For professional use only. "
        "Data sources: EU PVGIS, OpenTopoData (EU-DEM 25m), OpenStreetMap.",
        ParagraphStyle("Ft", parent=styles["Normal"], fontSize=7, textColor=colors.grey)
    ))

    doc.build(story)
    buf.seek(0)
    return buf


# ─── UI Layout ────────────────────────────────────────────────────────────────

# ── Step 1: Project Type Selection ──────────────────────────────────────────
st.markdown("### Step 1 — Project Type")
st.caption("SiteIQ covers **ground-mounted Freifläche** only (no rooftop, DACH, floating or carport).")

pt_col1, pt_col2 = st.columns(2)

with pt_col1:
    land_use = st.radio(
        "**Land Use**",
        ["Standard Freifläche", "Agri-PV (Doppelnutzung)"],
        help="Standard = conventional ground-mount. Agri-PV = dual use with agriculture (elevated / bifacial)."
    )
    if land_use == "Agri-PV (Doppelnutzung)":
        st.success("✅ EEG 2023 Agri-PV bonus eligible · DIN SPEC 91434 applies")
    else:
        st.info("ℹ️ Standard EEG Freifläche tariff · No dual-use requirements")

with pt_col2:
    mount_type = st.radio(
        "**Mounting System**",
        ["Fixed Tilt", "Single-Axis Tracker"],
        help="Tracker systems require flatter terrain (≤6% slope) and more N-S row spacing."
    )
    if mount_type == "Single-Axis Tracker":
        st.warning("⚠️ Tracker: max recommended slope ≤ 6% · Higher CAPEX, higher yield")
    else:
        st.info("ℹ️ Fixed Tilt: max recommended slope ≤ 10% · Lower CAPEX")

# Normalise land_use key for logic
_land_use  = "Agri-PV" if "Agri-PV" in land_use else "Standard"
_mount_type = mount_type  # "Fixed Tilt" or "Single-Axis Tracker"

st.divider()
st.markdown("### Step 2 — Site Location")

left, right = st.columns([1, 2])

with left:
    st.subheader("📍 Site Input")
    method = st.radio("Input method", [
        "🗺️ Click on Map",
        "📐 Coordinates (Lat / Lon)",
        "🔗 Google Maps Link",
        "📁 Upload KML / KMZ File"
    ])

    lat = lon = None
    kml_area = None

    if method == "🗺️ Click on Map":
        st.caption("Click anywhere on the map to set the site location.")
        default_lat = st.session_state.get("map_lat", 48.5)
        default_lon = st.session_state.get("map_lon", 10.5)
        m = folium.Map(location=[default_lat, default_lon], zoom_start=5,
                       tiles="OpenStreetMap")
        # Show existing marker if already clicked
        if "map_lat" in st.session_state:
            folium.Marker(
                [st.session_state["map_lat"], st.session_state["map_lon"]],
                tooltip="Selected site",
                icon=folium.Icon(color="green", icon="leaf")
            ).add_to(m)
        map_result = st_folium(m, width=None, height=320, returned_objects=["last_clicked"])
        if map_result and map_result.get("last_clicked"):
            st.session_state["map_lat"] = map_result["last_clicked"]["lat"]
            st.session_state["map_lon"] = map_result["last_clicked"]["lng"]
        if "map_lat" in st.session_state:
            lat = st.session_state["map_lat"]
            lon = st.session_state["map_lon"]
            st.success(f"📌 Selected: {lat:.5f}°N, {lon:.5f}°E")
        else:
            st.info("👆 Click on the map to select a site location.")

    elif method == "📐 Coordinates (Lat / Lon)":
        lat = st.number_input("Latitude",  value=48.5665, format="%.5f")
        lon = st.number_input("Longitude", value=12.1521, format="%.5f")

    elif method == "🔗 Google Maps Link":
        st.caption("Right-click any point in Google Maps → 'Copy coordinates', or paste the page URL.")
        maps_url = st.text_input("Paste Google Maps link", placeholder="https://www.google.com/maps/@48.1351,11.5820,15z")
        if maps_url:
            lat, lon = parse_google_maps_url(maps_url)
            if lat and lon:
                st.success(f"📌 Extracted: {lat:.5f}°N, {lon:.5f}°E")
            else:
                st.warning("Could not extract coordinates.  \nTip: In Google Maps, right-click a point → the coordinates appear at the top of the menu — click them to copy, then paste here.")

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

    site_name = st.text_input("Site name / reference", placeholder="e.g. Site-Bavaria-2024-01")

    if kml_area:
        area_ha = st.number_input("Site area (hectares)", min_value=0.1, value=float(kml_area), step=0.5)
    else:
        area_ha = st.number_input("Site area (hectares)", min_value=0.1, value=10.0, step=0.5)

    go = st.button("🔍 Run Site Screening", type="primary", use_container_width=True)

with right:
    if go:
        # ── Validate location ──
        if lat is None or lon is None:
            st.error("Please select a site location using one of the input methods on the left.")
            st.stop()

        # ── Fetch data ──
        with st.spinner("Fetching solar resource data from EU PVGIS…"):
            solar = get_solar_data(lat, lon)
        with st.spinner("Analysing terrain & slope…"):
            terrain = get_terrain_data(lat, lon)

        # ── Assessments ──
        s_lbl, _, s_detail = assess_slope(terrain["max_slope_pct"] if terrain["success"] else 0, _mount_type)
        g_lbl, _, g_detail = assess_solar(solar["annual_ghi"]       if solar["success"]   else 0)
        country, eeg_status, eeg_note = assess_eeg(lat, lon, _land_use)
        cap_mw, cap_mwh = site_capacity(area_ha, _land_use, _mount_type)
        verdict, verdict_txt = overall_verdict(s_lbl, g_lbl)

        # ── Project type badge ──
        badge_color = "#1a5c2e" if _land_use == "Agri-PV" else "#1565c0"
        st.markdown(
            f'<span style="background:{badge_color};color:white;padding:3px 10px;border-radius:4px;font-size:0.8rem;">'
            f'{land_use} · {mount_type}</span>',
            unsafe_allow_html=True
        )
        st.markdown("")

        # ── Verdict banner ──
        if "✅" in verdict:
            st.success(f"**{verdict}** — {verdict_txt}")
        elif "⚠️" in verdict:
            st.warning(f"**{verdict}** — {verdict_txt}")
        else:
            st.error(f"**{verdict}** — {verdict_txt}")

        # ── Top metrics ──
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("☀️ Annual GHI",    f"{solar.get('annual_ghi','—')} kWh/m²")
        c2.metric("⛰️ Max Slope",     f"{terrain.get('max_slope_pct','—')}%")
        c3.metric("⚡ Est. Capacity",  f"{cap_mw} MWp")
        c4.metric("📐 Optimal Tilt",  f"{solar.get('optimal_tilt','—')}°")

        st.divider()

        # ── Detail columns ──
        d1, d2 = st.columns(2)
        with d1:
            st.markdown("**☀️ Solar Resource**")
            (st.success if "✅" in g_lbl else st.warning if "⚠️" in g_lbl else st.error)(g_detail)

            st.markdown("**🇪🇺 EEG / Regulatory**")
            st.info(f"{country}  \n{eeg_status}  \n_{eeg_note}_")

        with d2:
            st.markdown("**⛰️ Terrain & Slope**")
            (st.success if "✅" in s_lbl else st.warning if "⚠️" in s_lbl else st.error)(s_detail)

            st.markdown("**🌊 Flood Risk**")
            flood_risk, flood_detail, flood_portal, flood_portal_name = get_flood_risk(
                lat, lon, terrain.get("center_elev") if terrain["success"] else None
            )
            if "🔴" in flood_risk:
                st.error(f"**{flood_risk}**  \n{flood_detail}  \n[Check {flood_portal_name} ↗]({flood_portal})")
            elif "🟠" in flood_risk or "🟡" in flood_risk:
                st.warning(f"**{flood_risk}**  \n{flood_detail}  \n[Check {flood_portal_name} ↗]({flood_portal})")
            else:
                st.success(f"**{flood_risk}**  \n{flood_detail}  \n[Verify at {flood_portal_name} ↗]({flood_portal})")

        # ── Monthly chart ──
        if solar["success"] and solar.get("monthly"):
            st.divider()
            st.markdown("**📊 Monthly Solar Irradiation (kWh/m²)**")
            st.bar_chart(pd.DataFrame(solar["monthly"]).set_index("Month"))

        # ── PDF export ──
        st.divider()
        pdf = build_pdf(
            site_name=site_name or f"Site_{lat:.3f}_{lon:.3f}",
            lat=lat, lon=lon, area_ha=area_ha,
            solar=solar, terrain=terrain,
            country=country, eeg_status=eeg_status, eeg_note=eeg_note,
            slope_lbl=s_lbl, solar_lbl=g_lbl,
            verdict=verdict, verdict_txt=verdict_txt,
            cap_mw=cap_mw, cap_mwh=cap_mwh,
            land_use=_land_use, mount_type=_mount_type
        )
        st.download_button(
            label="⬇️  Download PDF Report",
            data=pdf,
            file_name=f"SiteIQ_{(site_name or 'report').replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True
        )

    else:
        st.markdown("""
        ### Welcome to SiteIQ 🌱

        Enter a site location on the left and click **Run Site Screening** to get:

        - ☀️ **Solar resource** — annual GHI, monthly breakdown, optimal tilt
        - ⛰️ **Terrain & slope** — max slope %, elevation (EU-DEM 25 m data)
        - 🇩🇪 **EEG eligibility** — Agri-PV bonus applicability check
        - ⚡ **Capacity estimate** — MWp & annual MWh at Agri-PV density
        - 📄 **PDF report** — one-click download, ready for client meetings

        ---
        *Data: EU PVGIS · OpenTopoData EU-DEM 25m · OpenStreetMap*
        *SiteIQ by PVMath — Module 1 of 5 | pvmath.com*
        """)
