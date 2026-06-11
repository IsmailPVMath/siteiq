import streamlit as st
import requests
import pandas as pd
import math
import io
from datetime import datetime
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
st.markdown('<p class="sub-header">Solar & Agri-PV Site Intelligence Platform — Worldwide</p>', unsafe_allow_html=True)
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


def assess_slope(pct):
    if pct <= 5:
        return "✅ Excellent", "green",  f"{pct}% — Ideal for Agri-PV trackers and fixed-tilt"
    elif pct <= 10:
        return "⚠️ Acceptable", "yellow", f"{pct}% — Feasible; higher earthworks cost expected"
    elif pct <= 15:
        return "⚠️ Challenging", "yellow", f"{pct}% — Significant earthworks required"
    else:
        return "❌ Critical", "red",    f"{pct}% — Too steep; likely not viable for Agri-PV"


def assess_solar(ghi):
    if ghi >= 1300:
        return "✅ Excellent", "green",  f"{ghi} kWh/m²/yr — Premium solar resource"
    elif ghi >= 1100:
        return "✅ Good",      "green",  f"{ghi} kWh/m²/yr — Good resource for DACH"
    elif ghi >= 900:
        return "⚠️ Moderate",  "yellow", f"{ghi} kWh/m²/yr — Viable but below DACH average"
    else:
        return "❌ Poor",      "red",    f"{ghi} kWh/m²/yr — Low resource; financial risk"


def assess_eeg(lat, lon):
    in_de = 47.3 <= lat <= 55.1 and  5.9 <= lon <= 15.1
    in_at = 46.4 <= lat <= 49.0 and  9.5 <= lon <= 17.2
    in_ch = 45.8 <= lat <= 47.8 and  5.9 <= lon <= 10.5
    if in_de:
        return "🇩🇪 Germany",     "✅ EEG 2023 Agri-PV bonus likely applicable", "Verify agricultural land class (§37 EEG)"
    elif in_at:
        return "🇦🇹 Austria",     "⚠️ Check OeMAG Agri-PV provisions",          "Austrian Renewable Energy Act applies"
    elif in_ch:
        return "🇨🇭 Switzerland", "⚠️ Check KEV/Pronovo Agri-PV rules",          "Swiss Energy Act provisions apply"
    else:
        return "🌍 Outside DACH", "❌ EEG not applicable",                        "Check local regulations"


def site_capacity(area_ha, density=0.35):
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
              cap_mw, cap_mwh):
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
        ["Site Name",   site_name or "—"],
        ["Coordinates", f"{lat:.5f}°N, {lon:.5f}°E"],
        ["Site Area",   f"{area_ha} ha"],
        ["Country",     country],
        ["Report Date", datetime.now().strftime("%d.%m.%Y")],
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
left, right = st.columns([1, 2])

with left:
    st.subheader("📍 Site Input")
    method = st.radio("Input method", ["Address / Location Name", "Coordinates (Lat / Lon)"])

    if method == "Address / Location Name":
        address  = st.text_input("Address or location", placeholder="e.g. Landshut, Bavaria, Germany")
        lat = lon = None
    else:
        address = None
        lat = st.number_input("Latitude",  value=48.5665, format="%.5f")
        lon = st.number_input("Longitude", value=12.1521, format="%.5f")

    site_name = st.text_input("Site name / reference", placeholder="e.g. Site-Bavaria-2024-01")
    area_ha   = st.number_input("Site area (hectares)", min_value=0.1, value=10.0, step=0.5)
    go        = st.button("🔍 Run Site Screening", type="primary", use_container_width=True)

with right:
    if go:
        # ── Geocode if needed ──
        if method == "Address / Location Name":
            if not address:
                st.error("Please enter an address.")
                st.stop()
            with st.spinner("Locating address…"):
                lat, lon, display = geocode_address(address)
            if lat is None:
                st.error("Could not find this location. Try coordinates instead.")
                st.stop()
            st.info(f"📌 {display}")

        # ── Fetch data ──
        with st.spinner("Fetching solar resource data from EU PVGIS…"):
            solar = get_solar_data(lat, lon)
        with st.spinner("Analysing terrain & slope…"):
            terrain = get_terrain_data(lat, lon)

        # ── Assessments ──
        s_lbl, _, s_detail = assess_slope(terrain["max_slope_pct"] if terrain["success"] else 0)
        g_lbl, _, g_detail = assess_solar(solar["annual_ghi"]       if solar["success"]   else 0)
        country, eeg_status, eeg_note = assess_eeg(lat, lon)
        cap_mw, cap_mwh = site_capacity(area_ha)
        verdict, verdict_txt = overall_verdict(s_lbl, g_lbl)

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
            st.warning("Manual check required → [Hochwasserportal](https://www.hochwasserportal.de/)  \n"
                       "_Automated flood-risk API coming in Module 2_")

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
            cap_mw=cap_mw, cap_mwh=cap_mwh
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
