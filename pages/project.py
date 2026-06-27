"""
pages/project.py — PVMath Project Setup Hub
Shared project context for SiteIQ, TerrainIQ, and YieldIQ.
Stores to st.session_state["pvm_project"].
"""

import io
import hashlib
import math
import re
import zipfile
import xml.etree.ElementTree as ET
import requests
import streamlit as st
import folium
from folium.plugins import Draw
from pvmath_styles import inject_styles
from pvmath_auth import save_project, ensure_db_session
from pvmath_session import clear_blank_project_flag
from pvmath_geocode import reverse_geocode, format_coords, label_from_display_name
from pvmath_boundary_ui import render_grouped_boundary_manager
from pvmath_folium_draw import (
    draw_signature,
    polygon_from_map_result,
    st_folium_pin_drop,
    st_folium_with_draw,
)
from pvmath_kml import (
    BOUNDARY_COLORS,
    apply_site_areas_only_selection,
    boundaries_from_kmz_latlon,
    filter_boundary_list,
    guess_boundary_enabled,
)

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


def _pin_coord_sig(lat: float, lon: float) -> str:
    return f"{lat:.5f},{lon:.5f}"


def _short_nominatim_label(display: str) -> str:
    return label_from_display_name(display)


def _resolve_pin_label(lat: float, lon: float, prefer: str = "") -> str:
    """Human-readable place label for the map pin (cached per coordinate)."""
    sig = _pin_coord_sig(lat, lon)
    if st.session_state.get("proj_pin_label_sig") == sig:
        cached = st.session_state.get("proj_pin_label")
        if cached:
            return cached
    label = _short_nominatim_label(prefer) if prefer else ""
    if not label:
        label = reverse_geocode(lat, lon) or ""
    st.session_state["proj_pin_label"] = label
    st.session_state["proj_pin_label_sig"] = sig
    return label


def _set_proj_pin(lat: float, lon: float, *, label: str = "", center_map: bool = True) -> bool:
    """Update pin session state; return True if coordinates changed."""
    prev_lat = st.session_state.get("proj_pin_lat")
    prev_lon = st.session_state.get("proj_pin_lon")
    changed = (
        prev_lat is None
        or prev_lon is None
        or abs(prev_lat - lat) > 1e-6
        or abs(prev_lon - lon) > 1e-6
    )
    st.session_state["proj_pin_lat"] = lat
    st.session_state["proj_pin_lon"] = lon
    if center_map:
        st.session_state["proj_map_center"] = [lat, lon]
    if changed:
        new_sig = _pin_coord_sig(lat, lon)
        if label:
            st.session_state["proj_pin_label"] = _short_nominatim_label(label)
            st.session_state["proj_pin_label_sig"] = new_sig
        else:
            st.session_state.pop("proj_pin_label", None)
            st.session_state.pop("proj_pin_label_sig", None)
    return changed


def _format_pin_status(lat: float, lon: float) -> str:
    label = _resolve_pin_label(lat, lon)
    coords = format_coords(lat, lon)
    if label:
        return f"📌 **{label}** · {coords}"
    return f"📌 Site pin · {coords}"


def _format_site_location_line(lat: float, lon: float) -> str:
    """Human-readable place + signed coords (Quick and Full Mode)."""
    label = _resolve_pin_label(lat, lon)
    coords = format_coords(lat, lon)
    if label:
        return f"**{label}** · {coords}"
    return coords


def _format_boundary_status(
    lat: float,
    lon: float,
    *,
    n_boundaries: int = 1,
    total_ha=None,
    area_ha=None,
) -> str:
    loc = _format_site_location_line(lat, lon)
    if total_ha is not None:
        return (
            f"✅ **{n_boundaries}** boundar{'y' if n_boundaries == 1 else 'ies'} · "
            f"{loc} · Combined: **{total_ha:,.1f} ha**"
        )
    if area_ha is not None:
        return f"✅ Boundary drawn · {loc} · Area: **{area_ha:,.1f} ha**"
    return f"✅ Site · {loc}"


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


def _resolve_site_location(proj, lat, lon):
    """
    Site lat/lon for save and module routing.
    Priority: explicit inputs → map pin → saved project → largest enabled KMZ parcel.
    """
    if lat is not None and lon is not None:
        return lat, lon

    pin_lat = st.session_state.get("proj_pin_lat")
    pin_lon = st.session_state.get("proj_pin_lon")
    if pin_lat is not None and pin_lon is not None:
        return pin_lat, pin_lon

    if proj.get("lat") is not None and proj.get("lon") is not None:
        return proj["lat"], proj["lon"]

    boundaries = st.session_state.get("proj_boundaries", [])
    enabled = [b for b in boundaries if b.get("enabled")]
    if not enabled:
        enabled = [b for b in boundaries if b.get("coords")]
    if enabled:
        largest = max(enabled, key=lambda b: polygon_area_ha(b["coords"]))
        return centroid_of(largest["coords"])

    return None, None


def boundaries_union_area_ha(coords_list):
    """Combined area (ha) for one or more [lat, lon] rings."""
    polys = [p for p in coords_list if p and len(p) >= 3]
    if not polys:
        return 0.0
    if len(polys) == 1:
        return polygon_area_ha(polys[0])
    try:
        from shapely.geometry import Polygon as ShapelyPolygon
        from shapely.ops import unary_union
        shapes = []
        for coords in polys:
            lats = [c[0] for c in coords]
            mean_lat = sum(lats) / len(lats)
            lat_m = 111320.0
            lon_m = 111320.0 * math.cos(math.radians(mean_lat))
            pts = [(c[1] * lon_m, c[0] * lat_m) for c in coords]
            shapes.append(ShapelyPolygon(pts))
        return round(unary_union(shapes).area / 10_000, 2)
    except Exception:
        return round(sum(polygon_area_ha(p) for p in polys), 2)


def _visible_proj_boundaries(bounds, show_all: bool):
    if show_all:
        return bounds
    return [b for b in bounds if b.get("is_primary", True)]


def _render_proj_boundary_manager():
    all_bounds = st.session_state.get("proj_boundaries", [])
    if not all_bounds:
        return
    show_all = st.session_state.get("proj_show_all_layers", False)
    hidden_n = sum(1 for b in all_bounds if not b.get("is_primary", True))
    bounds = _visible_proj_boundaries(all_bounds, show_all)

    st.markdown("**Site boundaries** — check parcels to include in this project")
    if hidden_n and not show_all:
        st.caption(
            f"Showing **{len(bounds)}** site parcel{'s' if len(bounds) != 1 else ''} "
            f"(layout slivers & infrastructure hidden). "
            f"**{hidden_n}** other layers hidden."
        )
    else:
        st.caption(
            "Site parcels pre-selected. TerrainIQ and SiteIQ use checked boundaries."
        )

    if hidden_n:
        if not show_all:
            if st.button(
                f"Show all layers ({hidden_n} hidden)",
                use_container_width=True,
                key="proj_show_hidden",
            ):
                st.session_state["proj_show_all_layers"] = True
                st.rerun()
        elif st.button("Site parcels only", use_container_width=True, key="proj_hide_extra"):
            st.session_state["proj_show_all_layers"] = False
            st.rerun()

    def _smart_select(all_b, visible):
        visible_ids = {b["id"] for b in visible}
        targets = all_b if show_all else [b for b in all_b if b["id"] in visible_ids]
        apply_site_areas_only_selection(targets)

    def _clear():
        st.session_state["proj_boundaries"] = []
        st.session_state.pop("proj_polygon_draft", None)
        st.session_state.pop("proj_kml_upload_key", None)
        st.session_state.pop("proj_show_all_layers", None)
        st.session_state["proj_polygon_cleared"] = True

    remove_ids = render_grouped_boundary_manager(
        all_bounds=all_bounds,
        visible_bounds=bounds,
        area_fn=polygon_area_ha,
        key_prefix="proj",
        on_clear_all=_clear,
        smart_select_fn=_smart_select,
    )
    if remove_ids:
        st.session_state["proj_boundaries"] = [
            b for b in all_bounds if b["id"] not in remove_ids
        ]
        st.rerun()


def _map_viewport_from_boundaries(boundaries):
    """Center and zoom for enabled parcel overlays."""
    enabled = [b for b in boundaries if b.get("enabled")]
    if not enabled:
        enabled = [b for b in boundaries if b.get("coords")]
    if not enabled:
        return None, None
    lats = [c[0] for b in enabled for c in b["coords"]]
    lons = [c[1] for b in enabled for c in b["coords"]]
    return [sum(lats) / len(lats), sum(lons) / len(lons)], 13


def _stable_proj_map_key(is_full: bool) -> str:
    """Stable key — remounting the map on every parcel toggle breaks polygon drawing."""
    return "proj_map_full" if is_full else "proj_map_quick"


def _draw_signature(poly: list):
    return draw_signature(poly)


@st.fragment
def _render_proj_map_fragment(is_full: bool, show_search: bool, coord_center):
    """
    Map + draw tools in a Streamlit fragment.
    Draw mode MUST use st_folium_with_draw (pvmath_folium_draw) — never all_drawings.
    """
    proj = st.session_state.get("pvm_project", {})
    _proj_bounds = st.session_state.get("proj_boundaries", [])

    if st.session_state.get("proj_polygon_cleared"):
        polygon_coords = None
    elif st.session_state.get("proj_polygon_draft"):
        polygon_coords = st.session_state["proj_polygon_draft"]
    else:
        _enabled = [b["coords"] for b in _proj_bounds if b.get("enabled")]
        polygon_coords = _enabled[0] if _enabled else None

    if show_search:
        search_q = st.text_input(
            "Search by place name",
            placeholder="e.g. Munich, Bavaria  or  Rajasthan India",
            label_visibility="collapsed",
            key="proj_map_search_in",
        )
        if search_q and search_q != st.session_state.get("proj_last_search", ""):
            with st.spinner("Searching…"):
                slat, slon, display = geocode_address(search_q)
            st.session_state["proj_last_search"] = search_q
            if slat:
                st.session_state["proj_map_zoom"] = 13
                _set_proj_pin(slat, slon, label=display)
                st.rerun()
            else:
                st.warning("Location not found — try adding the country name.")

    if coord_center:
        _cc_sig = f"{coord_center[0]:.5f}|{coord_center[1]:.5f}"
        if st.session_state.get("proj_coord_jump_sig") != _cc_sig:
            st.session_state["proj_coord_jump_sig"] = _cc_sig
            st.session_state["proj_map_center"] = coord_center
            st.session_state["proj_map_zoom"] = 13
    elif _proj_bounds:
        _bc, _bz = _map_viewport_from_boundaries(_proj_bounds)
        if _bc:
            _bsig = ",".join(sorted(b["id"] for b in _proj_bounds if b.get("enabled")))
            if st.session_state.get("proj_bounds_jump_sig") != _bsig:
                st.session_state["proj_bounds_jump_sig"] = _bsig
                st.session_state["proj_map_center"] = _bc
                st.session_state["proj_map_zoom"] = _bz

    _pin_lat = st.session_state.get("proj_pin_lat")
    _pin_lon = st.session_state.get("proj_pin_lon")
    center = st.session_state.get("proj_map_center", proj.get("map_center_cache", [30.0, 10.0]))
    zoom = st.session_state.get("proj_map_zoom", 4)

    m = folium.Map(
        location=center,
        zoom_start=zoom,
        tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        attr="Google Satellite",
    )

    if is_full:
        Draw(
            export=False,
            position="topleft",
            draw_options={
                "polyline": False,
                "polygon": {"shapeOptions": {"color": "#f5c518", "weight": 4, "fillOpacity": 0.15}},
                "circle": False,
                "rectangle": False,
                "circlemarker": False,
                "marker": False,
            },
            edit_options={"edit": True, "remove": True},
        ).add_to(m)

    for _bi, _bb in enumerate(_proj_bounds):
        _bc = BOUNDARY_COLORS[_bi % len(BOUNDARY_COLORS)] if _bb.get("enabled") else "#888888"
        folium.Polygon(
            locations=[[c[0], c[1]] for c in _bb["coords"]],
            color=_bc,
            fill=True,
            fill_opacity=0.24 if _bb.get("enabled") else 0.05,
            weight=3 if _bb.get("enabled") else 1,
            dash_array=None if _bb.get("enabled") else "6,4",
            tooltip=_bb["name"],
        ).add_to(m)

    if polygon_coords and len(polygon_coords) >= 3 and not _proj_bounds:
        folium.Polygon(
            locations=[[c[0], c[1]] for c in polygon_coords],
            color="#f5c518",
            fill=True,
            fill_opacity=0.15,
            weight=4,
            tooltip="Site boundary",
        ).add_to(m)

    if _pin_lat is not None and _pin_lon is not None:
        folium.Marker(
            [_pin_lat, _pin_lon],
            tooltip="Site location",
            icon=folium.Icon(color="green", icon="star"),
        ).add_to(m)

    _map_key = _stable_proj_map_key(is_full)

    if is_full:
        st.caption(
            "Checked parcels are solid; unchecked are faint. "
            "Use the **polygon tool** (left toolbar) to draw a site boundary — "
            "click each vertex, then close the shape on the first point."
        )
        map_result = st_folium_with_draw(
            m,
            map_key=_map_key,
            center=center,
            zoom=zoom,
            height=420,
        )
        if map_result:
            _poly = polygon_from_map_result(map_result, lonlat=False)
            if _poly:
                _sig = _draw_signature(_poly)
                if _sig and st.session_state.get("proj_last_draw_sig") != _sig:
                    st.session_state["proj_last_draw_sig"] = _sig
                    st.session_state["proj_polygon_draft"] = _poly
                    st.session_state["proj_boundaries"] = [{
                        "id": "draw_1",
                        "name": "Drawn boundary",
                        "coords": _poly,
                        "enabled": True,
                    }]
                    _clat, _clon = centroid_of(_poly)
                    st.session_state["proj_pin_lat"] = _clat
                    st.session_state["proj_pin_lon"] = _clon
                    st.session_state.pop("proj_pin_label", None)
                    st.session_state.pop("proj_pin_label_sig", None)
                    _resolve_pin_label(_clat, _clon)
                    st.session_state.pop("proj_polygon_cleared", None)
                    st.session_state.pop("proj_kml_upload_key", None)
    else:
        st.caption(
            "**Single-click** the map to place the site pin (search also drops a pin). "
            "Boundary drawing and TerrainIQ require **Full Mode** above."
        )
        map_result = st_folium_pin_drop(
            m,
            map_key=_map_key,
            center=center,
            zoom=zoom,
            height=400,
        )
        if map_result and map_result.get("last_clicked"):
            lc = map_result["last_clicked"]
            if _set_proj_pin(lc["lat"], lc["lng"]):
                st.rerun()

    _pin_lat = st.session_state.get("proj_pin_lat")
    _pin_lon = st.session_state.get("proj_pin_lon")
    if st.session_state.get("proj_polygon_cleared"):
        polygon_coords = None
    elif st.session_state.get("proj_polygon_draft"):
        polygon_coords = st.session_state["proj_polygon_draft"]
    else:
        _enabled = [b["coords"] for b in _proj_bounds if b.get("enabled")]
        polygon_coords = _enabled[0] if _enabled else None

    _enabled_bounds = [b for b in _proj_bounds if b.get("enabled")]
    if _enabled_bounds:
        lat, lon = _resolve_site_location(proj, _pin_lat, _pin_lon)
        if lat is not None and lon is not None:
            _total = boundaries_union_area_ha([b["coords"] for b in _enabled_bounds])
            _ps1, _ps2 = st.columns([4, 1])
            with _ps1:
                st.success(
                    _format_boundary_status(
                        lat, lon,
                        n_boundaries=len(_enabled_bounds),
                        total_ha=_total,
                    )
                )
            with _ps2:
                if st.button("🗑️ Clear", use_container_width=True, help="Remove all boundaries",
                             key="proj_frag_clear_bounds"):
                    st.session_state.pop("proj_polygon_draft", None)
                    st.session_state.pop("proj_pin_lat", None)
                    st.session_state.pop("proj_pin_lon", None)
                    st.session_state.pop("proj_pin_label", None)
                    st.session_state.pop("proj_pin_label_sig", None)
                    st.session_state.pop("proj_kml_upload_key", None)
                    st.session_state.pop("proj_last_draw_sig", None)
                    st.session_state["proj_boundaries"] = []
                    st.session_state["proj_polygon_cleared"] = True
                    st.rerun()
    elif polygon_coords and len(polygon_coords) >= 3:
        lat = st.session_state.get("proj_pin_lat")
        lon = st.session_state.get("proj_pin_lon")
        if lat is not None and lon is not None:
            area_from_poly = polygon_area_ha(polygon_coords)
            _ps1, _ps2 = st.columns([4, 1])
            with _ps1:
                st.success(
                    _format_boundary_status(lat, lon, area_ha=area_from_poly)
                )
            with _ps2:
                if st.button("🗑️ Clear", use_container_width=True, help="Remove the drawn boundary",
                             key="proj_frag_clear_draw"):
                    st.session_state.pop("proj_polygon_draft", None)
                    st.session_state.pop("proj_pin_lat", None)
                    st.session_state.pop("proj_pin_lon", None)
                    st.session_state.pop("proj_pin_label", None)
                    st.session_state.pop("proj_pin_label_sig", None)
                    st.session_state.pop("proj_last_draw_sig", None)
                    st.session_state["proj_boundaries"] = []
                    st.session_state["proj_polygon_cleared"] = True
                    st.rerun()
    elif _pin_lat is not None and _pin_lon is not None:
        st.success(_format_pin_status(_pin_lat, _pin_lon))
    elif is_full:
        st.markdown(
            '<div style="background:#7a4800;color:#fff;border-radius:7px;padding:0.4rem 0.8rem;'
            'font-size:0.84rem;font-weight:600;margin-top:0.3rem;">'
            '✏️ Draw a polygon on the map, upload a KMZ, or enter coordinates above.</div>',
            unsafe_allow_html=True,
        )


def _proj_map_component_key(*, is_full, boundaries, pin_lat, pin_lon):
    en = ",".join(sorted(b["id"] for b in boundaries if b.get("enabled")))
    mode = "full" if is_full else "quick"
    pin = f"{pin_lat:.4f}_{pin_lon:.4f}" if pin_lat is not None and pin_lon is not None else "none"
    raw = f"{mode}|{en}|{pin}|{len(boundaries)}"
    if len(raw) > 150:
        raw = hashlib.sha256(raw.encode()).hexdigest()[:24]
    return f"proj_map_{raw}"


def parse_kml_polygon(data: bytes):
    """Extract the full boundary polygon (not just centroid) from raw KML bytes.
    Returns (coords [[lat, lon], ...], centroid_lat, centroid_lon, area_ha) or
    (None, None, None, None) if no usable polygon is found."""
    try:
        root = ET.fromstring(data)
        coords_el = root.find('.//{http://www.opengis.net/kml/2.2}coordinates')
        if coords_el is None:
            coords_el = root.find('.//coordinates')
        if coords_el is None or not coords_el.text:
            return None, None, None, None
        coords = []
        for token in coords_el.text.strip().split():
            parts = token.split(',')
            if len(parts) >= 2:
                coords.append([float(parts[1]), float(parts[0])])  # KML is lon,lat → [lat, lon]
        if len(coords) < 3:
            return None, None, None, None
        # Drop a closing vertex that duplicates the first (common in KML rings)
        if coords[0] == coords[-1] and len(coords) > 3:
            coords = coords[:-1]
        clat, clon = centroid_of(coords)
        area = polygon_area_ha(coords)
        return coords, clat, clon, area
    except Exception:
        return None, None, None, None


def parse_kmz_polygon(data: bytes):
    """KMZ is a zipped KML — unzip and delegate to parse_kml_polygon()."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            kml_name = next((n for n in z.namelist() if n.lower().endswith('.kml')), None)
            if kml_name:
                return parse_kml_polygon(z.read(kml_name))
    except Exception:
        pass
    return None, None, None, None


# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
inject_styles(accent="#1d9e52", accent_light="#d4e8d4")

st.markdown("""
<style>
div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #1d9e52, #145f34) !important;
    border: none !important; color: #fff !important;
}
.proj-mode-card {
    border: 2px solid #e0e8e0; border-radius: 12px;
    padding: 1.1rem 1.3rem; background: #fff; cursor: pointer;
    transition: border-color .2s, box-shadow .2s;
}
.proj-mode-card.active { border-color: #1d9e52; box-shadow: 0 0 0 3px rgba(29,158,82,.12); }
.proj-mode-card h4 { margin: 0 0 0.3rem 0; font-size: 1rem; font-weight: 700; color: #1a2e1a; }
.proj-mode-card p  { margin: 0; font-size: 0.84rem; color: #5a7a5a; line-height: 1.5; }
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
  <h1 style="font-size:2rem;font-weight:800;color:#1a2e1a;margin:0 0 0.3rem 0;">📋 Project Setup</h1>
  <p style="color:#5a7a5a;font-size:1rem;margin:0;">
    Enter project details once — SiteIQ, TerrainIQ, and YieldIQ will use this context automatically.
  </p>
</div>
""", unsafe_allow_html=True)

st.session_state["_pvm_active_page"] = "Project"

# ─────────────────────────────────────────────────────────────────────────────
# SHOW CURRENT PROJECT BANNER (if already set)
# ─────────────────────────────────────────────────────────────────────────────
proj = st.session_state.get("pvm_project", {})

# Pre-seed pin state from saved project so "Proceed" works without re-clicking map
if proj.get("lat") is not None and proj.get("lon") is not None:
    if "proj_pin_lat" not in st.session_state:
        st.session_state["proj_pin_lat"] = proj["lat"]
        st.session_state["proj_pin_lon"] = proj["lon"]
    if "proj_map_center" not in st.session_state:
        st.session_state["proj_map_center"] = [proj["lat"], proj["lon"]]
        st.session_state["proj_map_zoom"]   = 13


# ─────────────────────────────────────────────────────────────────────────────
# SETUP FORM — always visible so project can be updated at any time
# ─────────────────────────────────────────────────────────────────────────────
if True:
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

    _loc_label = proj.get("location_label", "")
    if proj.get("lat") and proj.get("lon"):
        _pin_preview = _loc_label or st.session_state.get("proj_pin_label", "")
        if not _pin_preview and st.session_state.get("proj_pin_lat") is not None:
            _pin_preview = _resolve_pin_label(proj["lat"], proj["lon"])
        st.caption(
            f"Resolved location: **{_pin_preview}**"
            if _pin_preview
            else "Location label appears below the map once you place a pin."
        )

    st.divider()

    # ── Mode selector ─────────────────────────────────────────────────────────
    st.markdown("**Analysis Mode**")
    # Use session state so clicking a card button persists across reruns
    if "proj_mode_sel" not in st.session_state:
        st.session_state["proj_mode_sel"] = proj.get("mode", "quick")
    current_mode = st.session_state["proj_mode_sel"]

    mode_col1, mode_col2 = st.columns(2)
    with mode_col1:
        is_q = current_mode == "quick"
        st.markdown(f"""
        <div style="border:2px solid {'#1d9e52' if is_q else '#e0e8e0'};border-radius:12px;
                    padding:1rem 1.2rem;background:{'#f0faf5' if is_q else '#fff'};
                    min-height:90px;">
          <h4 style="margin:0 0 0.3rem 0;font-size:1rem;font-weight:700;color:#1a2e1a;">
            ⚡ Quick Mode — Pin Drop</h4>
          <p style="margin:0;font-size:0.84rem;color:#5a7a5a;line-height:1.5;">
            <strong>Single-click</strong> to drop a site pin — no boundary drawing in this mode.
            Enables <strong>SiteIQ</strong> and <strong>YieldIQ</strong>.
            Switch to Full Mode for polygons and TerrainIQ.</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("✓ Select Quick Mode" if is_q else "Select Quick Mode",
                     key="btn_mode_quick", use_container_width=True,
                     type="primary" if is_q else "secondary"):
            st.session_state["proj_mode_sel"] = "quick"
            st.rerun()

    with mode_col2:
        is_f = current_mode == "full"
        st.markdown(f"""
        <div style="border:2px solid {'#1d9e52' if is_f else '#e0e8e0'};border-radius:12px;
                    padding:1rem 1.2rem;background:{'#f0faf5' if is_f else '#fff'};
                    min-height:90px;">
          <h4 style="margin:0 0 0.3rem 0;font-size:1rem;font-weight:700;color:#1a2e1a;">
            🗺️ Full Mode — Site Boundary</h4>
          <p style="margin:0;font-size:0.84rem;color:#5a7a5a;line-height:1.5;">
            Draw the site boundary polygon. Enables <strong>all 3 modules</strong> including
            <strong>TerrainIQ</strong> terrain extraction. For engineering work.</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("✓ Select Full Mode" if is_f else "Select Full Mode",
                     key="btn_mode_full", use_container_width=True,
                     type="primary" if is_f else "secondary"):
            st.session_state["proj_mode_sel"] = "full"
            st.rerun()

    is_full = current_mode == "full"

    st.divider()

    # ── Location input ────────────────────────────────────────────────────────
    st.markdown("**Site Location**")

    # In Full Mode the map method is for drawing, not just clicking
    _map_label = "🗺️ Draw on Map" if is_full else "🗺️ Search / Click on Map"
    loc_method = st.radio(
        "Input method",
        [_map_label, "📐 Coordinates (Lat / Lon)", "🔗 Google Maps Link", "📁 KML / KMZ Upload"],
        horizontal=True,
        label_visibility="collapsed",
    )
    _is_map = loc_method.startswith("🗺️")

    # Pre-fill from existing project so Proceed works without re-interacting with map
    lat = proj.get("lat")
    lon = proj.get("lon")
    # Read polygon: use draft if present; but if user hit "Clear" use None, not saved polygon
    # ── Boundaries list (multi-parcel KMZ support) ───────────────────────────
    if "proj_boundaries" not in st.session_state:
        if proj.get("polygon_boundaries"):
            st.session_state["proj_boundaries"] = filter_boundary_list(
                list(proj["polygon_boundaries"]), latlon=True
            )
        elif proj.get("polygon_coords"):
            st.session_state["proj_boundaries"] = [{
                "id": "saved_0",
                "name": "Site boundary",
                "coords": proj["polygon_coords"],
                "enabled": True,
            }]
        else:
            st.session_state["proj_boundaries"] = []

    if st.session_state.get("proj_polygon_cleared"):
        polygon_coords = None
    elif st.session_state.get("proj_polygon_draft"):
        polygon_coords = st.session_state["proj_polygon_draft"]
    else:
        _enabled = [b["coords"] for b in st.session_state["proj_boundaries"] if b.get("enabled")]
        polygon_coords = _enabled[0] if len(_enabled) == 1 else (_enabled[0] if _enabled else None)

    # ── Coordinate / Google Maps inputs (used to centre map in Full Mode too) ──
    _coord_center = None  # [lat, lon] to jump map to

    if loc_method == "📐 Coordinates (Lat / Lon)":
        _c1, _c2 = st.columns(2)
        with _c1:
            lat = st.number_input("↕️ Latitude",  value=proj.get("lat", 48.5665), format="%.5f", key="proj_lat_in")
        with _c2:
            lon = st.number_input("↔️ Longitude", value=proj.get("lon", 12.1521), format="%.5f", key="proj_lon_in")
        _coord_center = [lat, lon]
        st.session_state["proj_pin_lat"] = lat
        st.session_state["proj_pin_lon"] = lon
        st.caption("Map below shows this location — click the map to fine-tune the pin.")

    elif loc_method == "🔗 Google Maps Link":
        maps_raw = st.text_input(
            "Paste Google Maps URL or coordinates",
            placeholder="17.1401, 78.4802  or  https://maps.google.com/...",
            label_visibility="collapsed",
        )
        if maps_raw:
            lat, lon = parse_google_maps_url(maps_raw)
            if lat is not None and lon is not None:
                st.success(f"📌 Extracted: {lat:.5f}°N, {lon:.5f}°E")
                _coord_center = [lat, lon]
                st.session_state["proj_pin_lat"] = lat
                st.session_state["proj_pin_lon"] = lon
                st.caption("Map below shows this location — click the map to fine-tune the pin.")
            else:
                st.warning("Could not parse. Try pasting coordinates as '48.137, 11.576'.")

    elif loc_method == "📁 KML / KMZ Upload":
        kml_file = st.file_uploader(
            "Upload site boundary file",
            type=["kml", "kmz"],
            label_visibility="collapsed",
            help="Export a polygon boundary from Google Earth, QGIS, or your GIS tool as .kml or .kmz.",
        )
        if kml_file is not None:
            _file_key = f"{kml_file.name}_{kml_file.size}"
            if st.session_state.get("proj_kml_upload_key") != _file_key:
                _raw = kml_file.read()
                _bounds, _hidden, _total = boundaries_from_kmz_latlon(_raw, _file_key)
                _primary = [b for b in _bounds if b.get("is_primary", True)]

                if not _primary and not _bounds:
                    st.warning(
                        "No site boundaries found. Ensure the KMZ contains closed "
                        "boundary polylines or polygons."
                    )
                else:
                    st.session_state["proj_boundaries"] = _bounds
                    st.session_state["proj_kml_upload_key"] = _file_key
                    st.session_state["proj_show_all_layers"] = not bool(_primary) and bool(_bounds)
                    st.session_state.pop("proj_polygon_draft", None)
                    st.session_state.pop("proj_polygon_cleared", None)
                    st.session_state.pop("proj_last_draw_sig", None)

                    _enabled = [b for b in _bounds if b["enabled"]]
                    if _enabled:
                        _primary = _primary or _bounds
                        _primary_en = [b for b in _enabled if b.get("is_primary", True)] or _enabled
                        _p = max(_primary_en, key=lambda b: polygon_area_ha(b["coords"]))
                        lat, lon = centroid_of(_p["coords"])
                        polygon_coords = _p["coords"]
                        st.session_state["proj_pin_lat"] = lat
                        st.session_state["proj_pin_lon"] = lon
                        _coord_center = [lat, lon]
                        _total_area = boundaries_union_area_ha([b["coords"] for b in _enabled])
                        msg = (
                            f"✅ Loaded **{len(_primary) or len(_bounds)}** site parcel"
                            f"{'s' if (len(_primary) or len(_bounds)) != 1 else ''}"
                        )
                        if _hidden:
                            msg += f" · **{_hidden}** layout layers hidden"
                        msg += f" · **{_total_area:,.1f} ha** combined"
                        st.success(msg)
                    else:
                        st.info(
                            f"Loaded **{len(_primary) or len(_bounds)}** shapes — "
                            f"check site parcels below."
                        )
                    st.rerun()
        st.caption("Imported parcels appear on the map below — use the layer tree to include or exclude.")

    _proj_bounds = st.session_state.get("proj_boundaries", [])
    if _proj_bounds:
        _render_proj_boundary_manager()
        lat, lon = _resolve_site_location(proj, lat, lon)
        if lat is not None and lon is not None:
            st.session_state["proj_pin_lat"] = lat
            st.session_state["proj_pin_lon"] = lon

    # ── Unified map (fragment — no full-page dim while drawing vertices) ───
    _render_proj_map_fragment(is_full, _is_map, _coord_center)

    if st.session_state.get("proj_polygon_cleared"):
        polygon_coords = None
    elif st.session_state.get("proj_polygon_draft"):
        polygon_coords = st.session_state["proj_polygon_draft"]
    else:
        _enabled = [
            b["coords"] for b in st.session_state.get("proj_boundaries", []) if b.get("enabled")
        ]
        polygon_coords = _enabled[0] if _enabled else None
    _plat = st.session_state.get("proj_pin_lat")
    _plon = st.session_state.get("proj_pin_lon")
    if _plat is not None and _plon is not None:
        lat, lon = _plat, _plon

    st.divider()

    # ── Area input ────────────────────────────────────────────────────────────
    area_ha_final = None
    _enabled_for_area = [
        b["coords"] for b in st.session_state.get("proj_boundaries", []) if b.get("enabled")
    ]
    if is_full and _enabled_for_area:
        area_from_poly = boundaries_union_area_ha(_enabled_for_area)
        n_b = len(_enabled_for_area)
        st.markdown(
            f"**Site Area** — auto-calculated from **{n_b}** "
            f"boundar{'y' if n_b == 1 else 'ies'}: **{area_from_poly:,.1f} ha**"
        )
        area_ha_final = area_from_poly
    elif is_full and polygon_coords and len(polygon_coords) >= 3:
        area_from_poly = polygon_area_ha(polygon_coords)
        st.markdown(f"**Site Area** — auto-calculated from boundary: **{area_from_poly} ha**")
        area_ha_final = area_from_poly
    else:
        # Clamp the stored value into [min_value, max_value] before handing it to
        # st.number_input — a stale/oversized area_ha (e.g. from a mis-drawn huge
        # polygon saved earlier in Full Mode) would otherwise raise an uncaught
        # StreamlitValueAboveMaxError and crash the whole page on load.
        _area_default = max(0.5, min(float(proj.get("area_ha", 10.0)), 50_000.0))
        area_ha_final = st.number_input(
            "Site Area (ha)",
            min_value=0.5, max_value=50_000.0,
            value=_area_default,
            step=1.0,
            help="Approximate gross site area. Used for capacity estimate in SiteIQ.",
        )

    # ── Save button ───────────────────────────────────────────────────────────
    st.markdown("")
    save_c1, save_c2 = st.columns([1, 3])
    with save_c1:
        save_clicked = st.button("💾 Save Project", type="primary", use_container_width=True)

    if save_clicked:
        lat, lon = _resolve_site_location(proj, lat, lon)
        if lat is None or lon is None:
            st.error(
                "Please set a site location — upload a KMZ with boundaries, drop a pin on the map, "
                "or enter coordinates."
            )
        elif not proj_name.strip():
            st.error("Please enter a project name.")
        else:
            mode_val = "full" if is_full else "quick"
            _bounds_save = st.session_state.get("proj_boundaries", [])
            _enabled_save = [b for b in _bounds_save if b.get("enabled")]
            _primary_poly = None
            if _enabled_save:
                _primary_poly = max(
                    _enabled_save, key=lambda b: polygon_area_ha(b["coords"])
                )["coords"]
            elif polygon_coords:
                _primary_poly = polygon_coords

            _loc_resolved = (
                reverse_geocode(lat, lon)
                if lat is not None and lon is not None
                else None
            ) or st.session_state.get("pvm_project", {}).get("location_label", "")

            _proj_data = {
                "name":           proj_name.strip(),
                "country":        proj_country.strip(),
                "location_label": _loc_resolved,
                "lat":            lat,
                "lon":            lon,
                "area_ha":        area_ha_final,
                "mode":           mode_val,
                "polygon_coords": _primary_poly if is_full else None,
                "polygon_boundaries": _bounds_save if is_full else None,
                "map_center_cache": [lat, lon],
            }
            from pvmath_topo_cache import boundary_fingerprint_from_boundaries
            _new_fp = boundary_fingerprint_from_boundaries(_bounds_save) if is_full else ""
            _proj = st.session_state.get("pvm_project", {})
            _old_cache = _proj.get("terrainiq_cache") or _proj.get("topoiq_cache")
            if (
                _old_cache
                and _new_fp
                and _old_cache.get("boundary_fp") == _new_fp
                and _old_cache.get("analysis_mode") == "parcels"
            ):
                _proj_data["terrainiq_cache"] = _old_cache
            st.session_state["pvm_project"] = _proj_data
            st.session_state["proj_edit_mode"] = False
            clear_blank_project_flag(st.session_state)
            # Persist to Supabase so project survives browser back / refresh.
            # If we already have a row id (this project was opened from My
            # Projects, or saved before in this session), update that same
            # row — otherwise insert a new row so it shows up as a new entry
            # in My Projects rather than overwriting an existing project.
            _uid = ensure_db_session(force_refresh=True)
            _persist_ok = True
            if not _uid:
                _persist_ok = False
                st.session_state["pvm_save_fail_reason"] = "session"
            if _uid:
                _existing_row_id = st.session_state.get("pvm_project_row_id")
                # pvm_project_row_id lingers in session_state after a save and
                # is only ever cleared by the Overview page's "+ New Project"
                # button. If the user instead just edits the name/location
                # fields in place on THIS page and saves again — e.g. Project
                # 5 in Germany, then straight into Project 6 in Austria
                # without going back to Overview first — that stale row id
                # caused every subsequent save to PATCH the same row instead
                # of inserting a new one, so only the latest project ever
                # showed up in My Projects. Compare against the identity of
                # whatever project that row id was last saved as: if the
                # name/lat/lon no longer match, this is a different project,
                # so force a fresh insert instead of overwriting it.
                _prev_snapshot = st.session_state.get("pvm_saved_snapshot")
                if _existing_row_id and _prev_snapshot and (
                    _prev_snapshot.get("name") != _proj_data["name"]
                    or _prev_snapshot.get("lat") != _proj_data["lat"]
                    or _prev_snapshot.get("lon") != _proj_data["lon"]
                ):
                    _existing_row_id = None
                _row_id = save_project(_uid, _proj_data, row_id=_existing_row_id)
                if _row_id:
                    st.session_state["pvm_project_row_id"] = _row_id
                    st.session_state["pvm_saved_snapshot"] = dict(_proj_data)
                else:
                    # save_project() returned None — the Supabase write did NOT
                    # go through (failed insert/update). Previously this was
                    # silently swallowed and the UI still showed a green
                    # "saved" toast, which is exactly why new projects weren't
                    # showing up in My Projects. Surface it instead of lying.
                    _persist_ok = False
                    st.session_state["pvm_save_fail_reason"] = "db"
            # Clear per-module map state so they recentre on new project location
            for key in ["map_center", "map_zoom", "map_lat", "map_lon", "last_map_search",
                        "proj_polygon_draft", "proj_polygon_cleared"]:
                st.session_state.pop(key, None)
            if _persist_ok:
                # NOTE: calling st.toast() here and then st.rerun() on the very
                # next line was why "Save Project" appeared to do nothing — the
                # rerun aborts this script run (via Streamlit's RerunException)
                # before the toast element reliably reaches the frontend, so it
                # either never shows or flashes for a fraction of a second.
                # Fix: stash the message and render the toast AFTER the rerun
                # instead, same pattern already used below for save failures.
                st.session_state["pvm_save_success_msg"] = (
                    f"✅ Project saved — {proj_name.strip()} · {mode_val.title()} Mode"
                )
            else:
                st.session_state["pvm_save_failed"] = True
            st.rerun()

    _save_success_msg = st.session_state.pop("pvm_save_success_msg", None)
    if _save_success_msg:
        st.toast(_save_success_msg, icon="✅")

    if st.session_state.pop("pvm_save_failed", False):
        _fail_reason = st.session_state.pop("pvm_save_fail_reason", "db")
        if _fail_reason == "session":
            st.error(
                "⚠️ Saved to this session, but your sign-in had momentarily dropped "
                "(common after the page sits idle for a bit while drawing a boundary), "
                "so it could NOT be written to your account database — it won't appear "
                "in My Projects or survive a refresh. Please click **Save Project** "
                "again now that the page is active; if it keeps happening, refresh the "
                "page once and re-save."
            )
        else:
            st.error(
                "⚠️ Saved to this session, but the project could NOT be written to your "
                "account database — it will not appear in My Projects and won't survive a "
                "refresh. This usually means the `user_projects` table in Supabase is "
                "missing an INSERT policy for authenticated users, or still has a UNIQUE "
                "constraint on `user_id` blocking more than one saved project per account. "
                "Check the Supabase table editor / RLS policies, or share the error from "
                "Streamlit Cloud logs."
            )

# ─────────────────────────────────────────────────────────────────────────────
# STATUS BAR + MODULE BUTTONS — shown below Save button after project is saved
# ─────────────────────────────────────────────────────────────────────────────
_saved = st.session_state.get("pvm_project", {})
if _saved.get("lat") is not None:
    _is_quick = _saved.get("mode") == "quick"
    topo_ok   = (not _is_quick) and bool(
        _saved.get("polygon_boundaries") or _saved.get("polygon_coords")
    )
    mode_str  = "Quick Mode" if _is_quick else "Full Mode"
    area_str  = f" · {_saved.get('area_ha')} ha" if _saved.get("area_ha") else ""

    st.markdown("")
    st.markdown(f"""
    <div style="background:#f0faf5;border:1.5px solid #b2dfca;border-radius:10px;
                padding:0.65rem 1rem;margin-bottom:0.6rem;">
      <span style="color:#1d9e52;font-size:0.8rem;">●</span>
      &nbsp;<strong style="color:#1a2e1a;font-size:0.9rem;">{_saved.get('name', 'Project')}</strong>
      <span style="color:#5a7a5a;font-size:0.85rem;">
        &nbsp;·&nbsp;{_saved.get('country', '')}
        &nbsp;·&nbsp;{mode_str}{area_str}
      </span>
    </div>
    """, unsafe_allow_html=True)

    _nc1, _nc2, _nc3 = st.columns(3)
    with _nc1:
        if st.button("🌍 SiteIQ", use_container_width=True, key="sb_siteiq"):
            st.switch_page("pages/siteiq.py")
    with _nc2:
        if st.button("⚡ YieldIQ", use_container_width=True, key="sb_yieldiq"):
            st.switch_page("pages/yieldiq.py")
    with _nc3:
        if _is_quick:
            _topo_lbl = "⛰️ TerrainIQ — Full Mode only"
        elif not topo_ok:
            _topo_lbl = "⛰️ TerrainIQ — needs boundary"
        else:
            _topo_lbl = "⛰️ TerrainIQ"
        if st.button(_topo_lbl, use_container_width=True, disabled=not topo_ok, key="sb_terrainiq"):
            st.switch_page("pages/terrainiq.py")

    if _is_quick:
        st.caption("TerrainIQ is only available in Full Mode with a drawn site boundary.")
    elif not topo_ok:
        st.caption("TerrainIQ requires a drawn site boundary. Update project below to add one.")

# ─────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="margin-top:2rem;padding-top:1rem;border-top:1px solid #e0e8e0;
            font-size:0.78rem;color:#8a9a8a;text-align:center;">
  Module 1 of 3 · SiteIQ &nbsp;·&nbsp; Module 2 of 3 · TerrainIQ &nbsp;·&nbsp; Module 3 of 3 · YieldIQ<br>
  PVMath-Solar Site Intelligence Platform · pvmath.com
</div>
""", unsafe_allow_html=True)
