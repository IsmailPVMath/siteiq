"""
pages/project.py — PVMath Project Setup Hub
Shared project context for SiteIQ, TopoIQ, and YieldIQ.
Stores to st.session_state["pvm_project"].
"""

import math
import re
import requests
import streamlit as st
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def geocode_address(query: str):
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": "SiteIQ/1.0 (pvmath.com; contact@pvmath.com)"},
            timeout=10,
        )
        data = r.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"]), data[0].get("display_name", "")
    except Exception:
        pass
    return None, None, ""


def parse_google_maps_url(raw: str):
    raw = raw.strip()
    m = re.match(r"^(-?\d{1,3}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)$", raw)
    if m:
        return float(m.group(1)), float(m.group(2))
    for pat in [
        r"@(-?\d+\.?\d+),(-?\d+\.?\d+)",
        r"[?&]q=(-?\d+\.?\d+),(-?\d+\.?\d+)",
        r"ll=(-?\d+\.?\d+),(-?\d+\.?\d+)",
        r"place/[^/]+/@(-?\d+\.?\d+),(-?\d+\.?\d+)",
    ]:
        m = re.search(pat, raw)
        if m:
            return float(m.group(1)), float(m.group(2))
    return None, None


def polygon_area_ha(coords):
    """Approximate polygon area in hectares via spherical shoelace formula."""
    if len(coords) < 3:
        return 0.0
    R = 6_371_000
    n = len(coords)
    area = 0.0
    for i in range(n):
        lat1 = math.radians(coords[i][0])
        lon1 = math.radians(coords[i][1])
        lat2 = math.radians(coords[(i + 1) % n][0])
        lon2 = math.radians(coords[(i + 1) % n][1])
        area += (lon2 - lon1) * (2 + math.sin(lat1) + math.sin(lat2))
    return round(abs(area) * R * R / 2 / 10_000, 2)


def centroid_of(coords):
    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]
    return sum(lats) / len(lats), sum(lons) / len(lons)


# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
html, body, [class*="css"] {
    font-family: 'Inter','Segoe UI',system-ui,sans-serif !important;
    font-size: 16px !important;
}
[data-testid="stTextInput"] label,
[data-testid="stNumberInput"] label,
[data-testid="stRadio"] label > div {
    font-size: 0.97rem !important; font-weight: 600 !important; color: #2a3820 !important;
}
div[data-testid="stButton"] > button {
    border-radius: 8px !important; font-weight: 600 !important; font-size: 0.97rem !important;
}
.proj-mode-card {
    border: 2px solid #e0e8e0; border-radius: 12px;
    padding: 1.1rem 1.3rem; background: #fff; cursor: pointer;
    transition: border-color .2s, box-shadow .2s;
}
.proj-mode-card.active { border-color: #1d9e52; box-shadow: 0 0 0 3px rgba(29,158,82,.12); }
.proj-mode-card h4 { margin: 0 0 0.3rem 0; font-size: 1rem; font-weight: 700; color: #1a2e1a; }
.proj-mode-card p  { margin: 0; font-size: 0.84rem; color: #5a7a5a; line-height: 1.5; }
.project-banner {
    background: linear-gradient(135deg, #1d9e52, #145f34);
    border-radius: 12px; padding: 1.2rem 1.6rem; color: #fff;
    display: flex; align-items: center; gap: 1.2rem; margin-bottom: 1.5rem;
}
.project-banner h3 { margin: 0; font-size: 1.1rem; font-weight: 800; letter-spacing: -0.02em; }
.project-banner p  { margin: 0.2rem 0 0 0; font-size: 0.85rem; opacity: 0.85; }
.module-btn {
    display: inline-block; padding: 0.55rem 1.1rem; border-radius: 8px;
    font-weight: 700; font-size: 0.88rem; text-decoration: none;
    border: none; cursor: pointer; margin-right: 0.5rem; margin-top: 0.7rem;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="padding:1.5rem 0 0.5rem 0;border-bottom:2px solid #e8f5ee;margin-bottom:1.5rem;">
  <div style="font-size:0.75rem;font-weight:700;text-transform:uppercase;
              letter-spacing:0.12em;color:#1d9e52;margin-bottom:0.3rem;">Project Setup</div>
  <h1 style="font-size:2rem;font-weight:800;color:#1a2e1a;margin:0 0 0.3rem 0;">📋 New Project</h1>
  <p style="color:#5a7a5a;font-size:1rem;margin:0;">
    Enter project details once — SiteIQ, TopoIQ, and YieldIQ will use this context automatically.
  </p>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SHOW CURRENT PROJECT BANNER (if already set)
# ─────────────────────────────────────────────────────────────────────────────
proj = st.session_state.get("pvm_project", {})
if proj.get("lat"):
    mode_badge = "⚡ Quick Mode" if proj.get("mode") == "quick" else "🗺️ Full Mode"
    boundary_info = f" · {proj.get('area_ha', '—')} ha" if proj.get("area_ha") else ""
    st.markdown(f"""
    <div class="project-banner">
      <div style="font-size:2rem;">✅</div>
      <div>
        <h3>{proj.get('name', 'Unnamed Project')}</h3>
        <p>{proj.get('country', '')} · {proj.get('lat', 0):.5f}°N, {proj.get('lon', 0):.5f}°E{boundary_info} · {mode_badge}</p>
      </div>
    </div>
    """, unsafe_allow_html=True)

    nav_c1, nav_c2, nav_c3, nav_c4 = st.columns(4)
    with nav_c1:
        if st.button("🌍 Open SiteIQ", use_container_width=True, type="primary"):
            st.switch_page("pages/siteiq.py")
    with nav_c2:
        yiq_disabled = False
        if st.button("⚡ Open YieldIQ", use_container_width=True):
            st.switch_page("pages/yieldiq.py")
    with nav_c3:
        topo_ok = proj.get("mode") == "full" and proj.get("polygon_coords")
        topo_label = "⛰️ Open TopoIQ" if topo_ok else "⛰️ TopoIQ (needs boundary)"
        if st.button(topo_label, use_container_width=True, disabled=not topo_ok):
            st.switch_page("pages/topoiq.py")
    with nav_c4:
        if st.button("✏️ Edit Project", use_container_width=True):
            st.session_state["proj_edit_mode"] = True
            st.rerun()

    if not st.session_state.get("proj_edit_mode", False):
        if not topo_ok:
            st.info("⛰️ **TopoIQ requires Full Mode:** Switch to Full Mode below and draw the site boundary to enable terrain analysis.")
        st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# SETUP FORM
# ─────────────────────────────────────────────────────────────────────────────
show_form = not proj.get("lat") or st.session_state.get("proj_edit_mode", False)

if show_form:
    # ── Project name + country ────────────────────────────────────────────────
    f1, f2 = st.columns(2)
    with f1:
        proj_name = st.text_input(
            "Project Name",
            value=proj.get("name", ""),
            placeholder="e.g. Bavaria North – Site A",
        )
    with f2:
        proj_country = st.text_input(
            "Project Country",
            value=proj.get("country", ""),
            placeholder="e.g. Germany, Italy, Spain…",
        )

    st.divider()

    # ── Mode selector ─────────────────────────────────────────────────────────
    st.markdown("**Analysis Mode**")
    mode_col1, mode_col2 = st.columns(2)
    current_mode = proj.get("mode", "quick")

    with mode_col1:
        quick_active = "active" if current_mode == "quick" else ""
        st.markdown(f"""
        <div class="proj-mode-card {quick_active}">
          <h4>⚡ Quick Mode — Pin Drop</h4>
          <p>Drop a pin on the map. Enables <strong>SiteIQ</strong> and <strong>YieldIQ</strong>.
          Ideal for rapid pre-screening in client meetings. Under 2 minutes.</p>
        </div>
        """, unsafe_allow_html=True)

    with mode_col2:
        full_active = "active" if current_mode == "full" else ""
        st.markdown(f"""
        <div class="proj-mode-card {full_active}">
          <h4>🗺️ Full Mode — Site Boundary</h4>
          <p>Draw the site boundary polygon. Enables <strong>all 3 modules</strong> including
          <strong>TopoIQ</strong> terrain extraction. Recommended for engineering work.</p>
        </div>
        """, unsafe_allow_html=True)

    mode = st.radio(
        "Select mode",
        ["⚡ Quick Mode (pin drop)", "🗺️ Full Mode (draw site boundary)"],
        index=0 if current_mode == "quick" else 1,
        label_visibility="collapsed",
        horizontal=True,
    )
    is_full = "Full" in mode

    st.divider()

    # ── Location input ────────────────────────────────────────────────────────
    st.markdown("**Site Location**")
    loc_method = st.radio(
        "Input method",
        ["🗺️ Search / Click on Map", "📐 Coordinates (Lat / Lon)", "🔗 Google Maps Link"],
        horizontal=True,
        label_visibility="collapsed",
    )

    lat = lon = None
    polygon_coords = proj.get("polygon_coords")

    # ── MAP ───────────────────────────────────────────────────────────────────
    if loc_method == "🗺️ Search / Click on Map":
        search_q = st.text_input(
            "Search by place name",
            placeholder="e.g. Munich, Bavaria  or  Rajasthan India",
            label_visibility="collapsed",
        )
        if search_q and search_q != st.session_state.get("proj_last_search", ""):
            with st.spinner("Searching…"):
                slat, slon, _ = geocode_address(search_q)
            if slat:
                st.session_state["proj_map_center"] = [slat, slon]
                st.session_state["proj_map_zoom"]   = 13
                st.session_state["proj_last_search"] = search_q
                st.rerun()
            else:
                st.session_state["proj_last_search"] = search_q
                st.warning("Location not found — try adding the country name.")

        center = st.session_state.get("proj_map_center", proj.get("map_center_cache", [30.0, 10.0]))
        zoom   = st.session_state.get("proj_map_zoom",   4)

        m = folium.Map(
            location=center, zoom_start=zoom,
            tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
            attr="Google Satellite",
        )

        if is_full:
            # Draw plugin for polygon boundary
            Draw(
                export=False,
                position="topleft",
                draw_options={
                    "polyline":     False,
                    "polygon":      True,
                    "circle":       False,
                    "rectangle":    True,
                    "circlemarker": False,
                    "marker":       False,
                },
                edit_options={"edit": True, "remove": True},
            ).add_to(m)
            # Show existing polygon if any
            if polygon_coords and len(polygon_coords) >= 3:
                folium.Polygon(
                    locations=[[c[0], c[1]] for c in polygon_coords],
                    color="#1d9e52", fill=True, fill_opacity=0.15, weight=2,
                    tooltip="Current site boundary",
                ).add_to(m)
            st.caption("Draw a **polygon** or **rectangle** around the site boundary. Use the edit tool to adjust vertices.")
        else:
            # Pin drop
            if "proj_pin_lat" in st.session_state:
                folium.Marker(
                    [st.session_state["proj_pin_lat"], st.session_state["proj_pin_lon"]],
                    tooltip="Selected site",
                    icon=folium.Icon(color="green", icon="star"),
                ).add_to(m)
            st.caption("Click anywhere on the map to drop a pin on your site.")

        returned = ["last_clicked", "all_drawings"] if is_full else ["last_clicked"]
        map_result = st_folium(m, width=None, height=400, returned_objects=returned, key="proj_map")

        if map_result:
            if is_full:
                drawings = map_result.get("all_drawings") or []
                for drawing in drawings:
                    geom = drawing.get("geometry", {})
                    if geom.get("type") == "Polygon":
                        raw_coords = geom["coordinates"][0]
                        polygon_coords = [[c[1], c[0]] for c in raw_coords]  # GeoJSON is [lon,lat]
                        lat, lon = centroid_of(polygon_coords)
                        st.session_state["proj_pin_lat"] = lat
                        st.session_state["proj_pin_lon"] = lon
                        break
                # Also allow click to centre the map
                if map_result.get("last_clicked") and not polygon_coords:
                    lc = map_result["last_clicked"]
                    st.session_state["proj_map_center"] = [lc["lat"], lc["lng"]]
            else:
                if map_result.get("last_clicked"):
                    lc = map_result["last_clicked"]
                    st.session_state["proj_pin_lat"] = lc["lat"]
                    st.session_state["proj_pin_lon"] = lc["lng"]
                    st.session_state["proj_map_center"] = [lc["lat"], lc["lng"]]
                    st.rerun()

        if "proj_pin_lat" in st.session_state:
            lat = st.session_state["proj_pin_lat"]
            lon = st.session_state["proj_pin_lon"]
            if not is_full:
                st.success(f"📌 Pin: {lat:.5f}°N, {lon:.5f}°E")
            else:
                if polygon_coords:
                    area_from_poly = polygon_area_ha(polygon_coords)
                    st.success(f"✅ Boundary drawn · Centroid: {lat:.5f}°N, {lon:.5f}°E · Area: **{area_from_poly} ha**")
                else:
                    st.info("Draw a polygon around the site boundary on the map above.")

    elif loc_method == "📐 Coordinates (Lat / Lon)":
        _c1, _c2 = st.columns(2)
        with _c1:
            lat = st.number_input("Latitude",  value=proj.get("lat", 48.5665), format="%.5f", key="proj_lat_in")
        with _c2:
            lon = st.number_input("Longitude", value=proj.get("lon", 12.1521), format="%.5f", key="proj_lon_in")
        if is_full:
            st.info("Switch to 'Search / Click on Map' to draw a site boundary for Full Mode.")

    elif loc_method == "🔗 Google Maps Link":
        maps_raw = st.text_input(
            "Paste Google Maps URL or coordinates",
            placeholder="17.1401, 78.4802  or  https://maps.google.com/...",
            label_visibility="collapsed",
        )
        if maps_raw:
            lat, lon = parse_google_maps_url(maps_raw)
            if lat and lon:
                st.success(f"📌 Extracted: {lat:.5f}°N, {lon:.5f}°E")
            else:
                st.warning("Could not parse. Try pasting coordinates as '48.137, 11.576'.")

    st.divider()

    # ── Area input ────────────────────────────────────────────────────────────
    area_ha_final = None
    if is_full and polygon_coords and len(polygon_coords) >= 3:
        area_from_poly = polygon_area_ha(polygon_coords)
        st.markdown(f"**Site Area** — auto-calculated from boundary: **{area_from_poly} ha**")
        area_ha_final = area_from_poly
    else:
        area_ha_final = st.number_input(
            "Site Area (ha)",
            min_value=0.5, max_value=50_000.0,
            value=float(proj.get("area_ha", 10.0)),
            step=1.0,
            help="Approximate gross site area. Used for capacity estimate in SiteIQ.",
        )

    # ── Save button ───────────────────────────────────────────────────────────
    st.markdown("")
    save_c1, save_c2 = st.columns([1, 3])
    with save_c1:
        save_clicked = st.button("✅ Save Project", type="primary", use_container_width=True)

    if save_clicked:
        if not lat or not lon:
            st.error("Please select a site location before saving.")
        elif not proj_name.strip():
            st.error("Please enter a project name.")
        else:
            mode_val = "full" if is_full else "quick"
            st.session_state["pvm_project"] = {
                "name":           proj_name.strip(),
                "country":        proj_country.strip(),
                "lat":            lat,
                "lon":            lon,
                "area_ha":        area_ha_final,
                "mode":           mode_val,
                "polygon_coords": polygon_coords if is_full else None,
                "map_center_cache": [lat, lon],
            }
            st.session_state["proj_edit_mode"] = False
            # Clear per-module map state so they recentre on new project location
            for key in ["map_center", "map_zoom", "map_lat", "map_lon", "last_map_search"]:
                st.session_state.pop(key, None)
            st.success(f"✅ Project saved — **{proj_name.strip()}** · {mode_val.title()} Mode")
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="margin-top:2rem;padding-top:1rem;border-top:1px solid #e0e8e0;
            font-size:0.78rem;color:#8a9a8a;text-align:center;">
  Module 1 of 3 · SiteIQ &nbsp;·&nbsp; Module 2 of 3 · TopoIQ &nbsp;·&nbsp; Module 3 of 3 · YieldIQ<br>
  PVMath — Solar Site Intelligence · pvmath.com
</div>
""", unsafe_allow_html=True)
