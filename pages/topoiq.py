from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components
import numpy as np
import requests
import math
import io
import concurrent.futures
import json
from PIL import Image
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from datetime import datetime
from pvmath_auth import (
    show_paywall,
    increment_usage, is_over_limit, remaining, FREE_LIMIT,
    prepared_by_line, module_confidence_label, save_project,
)
from pvmath_topo_cache import build_topo_cache, persist_topo_cache, fingerprint_from_latlon_polys
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
MAX_GRID_POINTS_LAYOUT = 1_500_000  # keep requested spacing (e.g. 5 m) for layout sites
MAX_GRID_POINTS_FAST = 300_000      # legacy coarsen budget when auto-coarsen enabled
DEM_ZOOM_MIN = 11
DEM_ZOOM_MAX = 14
TILE_FETCH_WORKERS = 8
from pvmath_kml import BOUNDARY_COLORS, filter_boundary_list
from pvmath_terrain_report import (
    build_report_context,
    compute_terrain_extras,
    compute_terrain_drivers_summary,
    generate_pdf_report,
    render_slope_map_png,
    site_capacity_mwp,
    _verdict_from_mean,
    verdict_for_mount,
)
from pvmath_geocode import format_coords, resolve_location_label
from pvmath_yield import (
    fetch_yield_cross_ref_bundle,
    yield_cross_ref_topoiq_html,
    yield_cross_ref_topoiq_text,
)
from pvmath_topo_export import (
    build_reference_json,
    build_topo_export_zip,
    epsg_utm_wgs84,
    export_dxf_contours,
    export_landxml_utm,
    export_linear_units,
    export_xyz_geo,
    export_xyz_georef,
    export_xyz_local,
    latlon_to_utm,
    local_en_from_latlon,
    sanitize_topo_basename,
    utm_grids_from_latlon,
)
from pvmath_help import help_caption
from pvmath_capacity import (
    capacity_band,
    format_mwp_range,
    capacity_footnote_global,
    GCR_SCREEN_LO,
    GCR_SCREEN_HI,
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


def _extract_drawn_polygon(map_data):
    """Read the most recent completed polygon from Folium Draw output."""
    if not map_data:
        return None
    active = map_data.get("last_active_drawing")
    if active:
        geom = active.get("geometry", {})
        if geom.get("type") == "Polygon":
            ring = geom.get("coordinates", [[]])[0]
            if len(ring) >= 4:
                return [(c[0], c[1]) for c in ring]
        elif geom.get("type") == "LineString":
            pts = [(c[0], c[1]) for c in geom["coordinates"]]
            if len(pts) >= 3:
                if pts[0] != pts[-1]:
                    pts.append(pts[0])
                return pts
    if not map_data.get("all_drawings"):
        return None
    polygon_coords = None
    for feat in reversed(map_data["all_drawings"]):
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
    return polygon_coords


TOPO_MAP_KEY = "topo_boundary_map"


def _prune_stale_folium_maps():
    """Hide orphan folium iframes left by Streamlit SPA navigation or old dynamic keys."""
    components.html(
        """
        <script>
        (function () {
          try {
            var doc = window.parent.document;
            var frames = Array.from(
              doc.querySelectorAll('[data-testid="stCustomComponentV1"] iframe')
            );
            if (frames.length <= 1) return;
            for (var i = 0; i < frames.length - 1; i++) {
              var block = frames[i].closest('[data-testid="element-container"]');
              if (block) block.style.display = "none";
            }
          } catch (e) {}
        })();
        </script>
        """,
        height=0,
    )


def _render_topo_boundary_map(
    boundaries,
    *,
    height=400,
    show_reference_layers=False,
    analysis_polygon=None,
    enable_draw=False,
):
    """
    Parcel map from Project Setup (enabled parcels shown).
    In custom-boundary mode, faint reference layers + yellow analysis polygon + Draw tools.
    """
    if show_reference_layers:
        display_bounds = boundaries
    else:
        display_bounds = [b for b in boundaries if b.get("enabled")]

    all_lats, all_lons = [], []
    for b in display_bounds:
        all_lats.extend(c[1] for c in b["coords"])
        all_lons.extend(c[0] for c in b["coords"])
    if analysis_polygon:
        all_lats.extend(c[1] for c in analysis_polygon)
        all_lons.extend(c[0] for c in analysis_polygon)

    if not all_lats:
        if enable_draw:
            center = st.session_state.get("topo_center", [30.0, 10.0])
            zoom = st.session_state.get("topo_zoom", 3)
        else:
            return None
    else:
        center = [float(np.mean(all_lats)), float(np.mean(all_lons))]
        zoom = st.session_state.get("topo_zoom", 13)

    m = folium.Map(
        location=center,
        zoom_start=zoom,
        tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        attr="Google Satellite",
    )

    for i, b in enumerate(display_bounds):
        on = b.get("enabled", True)
        if show_reference_layers:
            color = BOUNDARY_COLORS[i % len(BOUNDARY_COLORS)] if on else "#999999"
            fill_opacity = 0.22 if on else 0.05
            weight = 2 if on else 1
            dash = None if on else "5,5"
        else:
            color = BOUNDARY_COLORS[i % len(BOUNDARY_COLORS)]
            fill_opacity = 0.28
            weight = 3
            dash = None
        folium.Polygon(
            locations=[(c[1], c[0]) for c in b["coords"]],
            color=color,
            fill=True,
            fill_opacity=fill_opacity,
            weight=weight,
            dash_array=dash,
            tooltip=f"{b['name']} ({'reference' if show_reference_layers and not on else 'selected'})",
        ).add_to(m)

    if analysis_polygon and len(analysis_polygon) >= 3 and not enable_draw:
        folium.Polygon(
            locations=[(c[1], c[0]) for c in analysis_polygon],
            color="#ffeb3b",
            fill=True,
            fill_opacity=0.18,
            weight=4,
            tooltip="Analysis boundary (drawn)",
        ).add_to(m)

    if enable_draw:
        _style = {
            "color": "#f5c518",
            "weight": 4,
            "opacity": 1.0,
            "fillColor": "#f5c518",
            "fillOpacity": 0.15,
        }
        Draw(
            export=False,
            position="topleft",
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
            edit_options={"edit": True, "remove": True},
        ).add_to(m)

    return st_folium(
        m,
        width=None,
        height=height,
        returned_objects=["last_active_drawing"] if enable_draw else [],
        key=TOPO_MAP_KEY,
        center=(center[0], center[1]),
        zoom=int(zoom),
    )


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


def _boundary_provenance(boundaries, proj) -> str:
    """Describe how the analysis boundary was defined."""
    n = len(boundaries) if boundaries else 0
    en = sum(1 for b in (boundaries or []) if b.get("enabled"))
    if proj.get("polygon_boundaries"):
        layers = len({b.get("layer_group") for b in boundaries if b.get("layer_group")})
        return (
            f"KMZ import via Project Setup · {en} enabled parcel{'s' if en != 1 else ''}"
            f"{' · ' + str(layers) + ' layers' if layers else ''}"
        )
    if n:
        return "Project Setup boundary · single polygon"
    return "User-defined boundary"


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
    <div class="pvmath-tagline">Tracker-aware terrain screening from Copernicus DEM — slope, cross-row grades, and client-ready PDFs before you order LiDAR.</div>
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
                           allow_coarsen: bool = False):
    """Keep requested spacing for layout; optional coarsen on very large sites."""
    max_points = MAX_GRID_POINTS_FAST if allow_coarsen else MAX_GRID_POINTS_LAYOUT
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat_c))
    width_m = max((p_e - p_w) * m_per_deg_lon, grid_m)
    height_m = max((p_n - p_s) * m_per_deg_lat, grid_m)
    n_cols = max(1, int(math.ceil(width_m / grid_m)))
    n_rows = max(1, int(math.ceil(height_m / grid_m)))
    points = n_rows * n_cols
    if points <= max_points:
        return float(grid_m)
    if not allow_coarsen:
        return None
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
                     polygon_coords=None, polygon_list=None, grid_m=5.0,
                     allow_coarsen: bool = False):
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

    grid_m = effective_grid_spacing(p_w, p_e, p_s, p_n, grid_m, lat_c, allow_coarsen=allow_coarsen)
    if grid_m is None:
        raise ValueError("GRID_TOO_LARGE")
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


# ─── Export functions → pvmath_topo_export.py ────────────────────────────────


def _boundaries_from_project(proj):
    """Read-only site boundaries from saved project (vertices as lon, lat tuples)."""
    if proj.get("polygon_boundaries"):
        loaded = filter_boundary_list(list(proj["polygon_boundaries"]), latlon=True)
        return [
            {
                "id": b.get("id", f"proj_{i}"),
                "name": b.get("name", f"Boundary {i + 1}"),
                "full_name": b.get("full_name", b.get("name", "")),
                "layer_group": b.get("layer_group"),
                "coords": [(c[1], c[0]) for c in b["coords"]],
                "enabled": b.get("enabled", True),
                "is_primary": b.get("is_primary", True),
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
            "is_primary": True,
        }]
    return []


# ─── Main UI ─────────────────────────────────────────────────────────────────

# ── Pre-populate from shared pvm_project ──────────────────────────────────
_proj = st.session_state.get("pvm_project", {})
_proj_name = _proj.get("name", "")
_proj_ctry = _proj.get("country", "")
_has_proj = _proj.get("lat") is not None and _proj.get("lon") is not None

if _proj.get("lat") and _proj.get("lon") and not st.session_state.get("topo_center"):
    st.session_state["topo_center"] = [_proj["lat"], _proj["lon"]]
    st.session_state["topo_zoom"] = 14

_boundaries = _boundaries_from_project(_proj)

if _has_proj:
    st.markdown(f"""
    <div style="background:#e8f5ee;border:1px solid #b8ddc8;border-radius:8px;
                padding:0.65rem 1rem;margin-bottom:0.9rem;font-size:0.89rem;color:#1a3a1a;">
      <strong>📋 Project:</strong>&nbsp; {_proj_name or "Unnamed"}
      &nbsp;·&nbsp; {_proj_ctry or "—"}
      &nbsp;·&nbsp; {format_coords(_proj["lat"], _proj["lon"])}
    </div>
    """, unsafe_allow_html=True)
elif not _has_proj:
    st.info(
        "Set up a project in **Project Setup** first — upload your KMZ or draw the site boundary there.",
        icon="ℹ️",
    )

_prev_page = st.session_state.get("_pvm_active_page")
st.session_state["_pvm_active_page"] = "TopoIQ"
if _prev_page != "TopoIQ":
    for _k in list(st.session_state.keys()):
        if _k.startswith("proj_map_"):
            st.session_state.pop(_k, None)
    _prune_stale_folium_maps()

left, right = st.columns([1, 1.4])

_enabled_polys = []
run = False
grid_spacing = 5
contour_minor = 0.5
contour_major = 1.0
allow_coarsen = False

with left:
    st.markdown(
        '<div class="section-hdr"><i class="fa-solid fa-layer-group" style="color:#1565c0;"></i> '
        'Analysis boundary</div>',
        unsafe_allow_html=True,
    )

    if not _has_proj:
        st.warning(
            "No project loaded. Open **Project Setup**, choose **Full Mode**, upload your KMZ "
            "(or draw a boundary), save, then return here."
        )
        if st.button("Go to Project Setup", type="primary", use_container_width=True, key="topo_go_proj"):
            st.switch_page("pages/project.py")
        _enabled_polys = []
    elif not _boundaries:
        st.warning(
            "This project has no site boundary yet. In **Project Setup**, switch to **Full Mode**, "
            "upload your KMZ or draw the boundary, and **Save Project**."
        )
        if st.button("Go to Project Setup", type="primary", use_container_width=True, key="topo_go_proj_empty"):
            st.switch_page("pages/project.py")
        _enabled_polys = []
    else:
        _enabled_n = sum(1 for b in _boundaries if b.get("enabled"))
        _total_ha = boundaries_union_area_ha(
            [b["coords"] for b in _boundaries if b.get("enabled")]
        ) if _enabled_n else 0.0
        st.markdown(
            '<div style="background:#e8f5ee;border:1.5px solid #b8ddc8;border-radius:10px;'
            'padding:0.75rem 1rem;margin-bottom:0.6rem;">'
            '<span style="font-weight:700;color:#145f34;font-size:0.88rem;">'
            '<i class="fa-solid fa-circle-check"></i> Boundaries from Project Setup</span><br>'
            '<span style="font-size:0.8rem;color:#3a5a3a;">'
            f'{_enabled_n} enabled parcel{"s" if _enabled_n != 1 else ""} '
            f'· {_total_ha:,.1f} ha — edit parcels in <strong>Project Setup</strong>, '
            'or draw a custom analysis polygon below.</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        if _enabled_n == 0:
            st.warning(
                "No parcels are enabled. Open **Project Setup**, check the parcels you want "
                "in the layer tree, and **Save Project**."
            )

        st.session_state.setdefault("topo_analysis_mode", "parcels")
        _mode_options = ("Project parcels", "Custom polygon (draw on map)")
        _cur_mode = st.session_state.get("topo_analysis_mode", "parcels")
        _mode_pick = st.radio(
            "Terrain analysis boundary",
            _mode_options,
            index=0 if _cur_mode == "parcels" else 1,
            horizontal=True,
            help="Use enabled parcels from Project Setup, or draw one polygon on the map for this run.",
        )
        st.session_state["topo_analysis_mode"] = (
            "parcels" if _mode_pick == _mode_options[0] else "drawn"
        )
        _use_draw = st.session_state["topo_analysis_mode"] == "drawn"

        if _use_draw:
            st.markdown(
                '<div style="background:rgba(255,235,59,0.12);border:1px solid rgba(200,160,0,0.35);'
                'border-radius:8px;padding:0.45rem 0.85rem;font-size:0.82rem;color:#5a4a00;'
                'margin-bottom:0.35rem;">'
                '<i class="fa-solid fa-pen-ruler" style="margin-right:0.4rem;"></i>'
                'Use the <strong>polygon tool</strong> (left toolbar) to draw your analysis boundary. '
                'Select a shape and use <strong>edit</strong> or <strong>delete</strong> in the toolbar.'
                '</div>',
                unsafe_allow_html=True,
            )
            _dc1, _dc2 = st.columns([1, 2])
            with _dc1:
                if st.button("Clear drawn boundary", key="topo_clear_drawn_poly", use_container_width=True):
                    st.session_state.pop("topo_analysis_polygon", None)
                    st.session_state.pop("topo_last_draw_sig", None)
                    st.rerun()
            if st.session_state.get("topo_analysis_polygon"):
                _saved_ha = boundary_area_ha(st.session_state["topo_analysis_polygon"])
                st.caption(
                    f"Saved analysis boundary: **{_saved_ha:,.1f} ha** — "
                    "draw a new polygon to replace it, or clear it."
                )
        else:
            st.caption("Map shows **enabled parcels from Project Setup** (read-only here).")

        with st.container(key="topoiq_map_panel"):
            _map_data = _render_topo_boundary_map(
                _boundaries,
                height=430,
                show_reference_layers=_use_draw,
                analysis_polygon=st.session_state.get("topo_analysis_polygon") if _use_draw else None,
                enable_draw=_use_draw,
            )
        _prune_stale_folium_maps()
        if _use_draw and _map_data:
            _drawn = _extract_drawn_polygon(_map_data)
            if _drawn:
                _sig = tuple(round(c[0], 5) for c in _drawn[: min(8, len(_drawn))])
                if st.session_state.get("topo_last_draw_sig") != _sig:
                    st.session_state["topo_last_draw_sig"] = _sig
                    st.session_state["topo_analysis_polygon"] = _drawn
                _da = boundary_area_ha(_drawn)
                if _da > MAX_SITE_AREA_HA:
                    st.error(_area_limit_message(_da))
                elif _da > 0:
                    st.success(
                        f"Analysis boundary — {len(_drawn) - 1} vertices · {_da:,.1f} ha"
                    )
            elif not st.session_state.get("topo_analysis_polygon"):
                st.caption("Draw your analysis boundary on the map above — polygon tool in the left toolbar.")

        if st.session_state.get("topo_analysis_mode") == "drawn":
            _ap = st.session_state.get("topo_analysis_polygon")
            _enabled_polys = [_ap] if _ap else []
        else:
            _enabled_polys = [b["coords"] for b in _boundaries if b.get("enabled")]

    if _boundaries:
        st.markdown(
            '<div class="section-hdr" style="margin-top:1rem;">'
            '<i class="fa-solid fa-sliders" style="color:#1565c0;"></i> Settings</div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="pvm-topo-settings"></div>', unsafe_allow_html=True)
        sc1, sc2, sc3 = st.columns(3)
        grid_spacing = sc1.slider(
            "Analysis grid (m)", min_value=3, max_value=10, value=5, step=1,
            help="Default 5 m for layout work. Copernicus GLO-30 is ~30 m native; "
                 "TopoIQ resamples to this spacing inside your boundary.",
        )
        contour_minor = sc2.slider("Minor contour (m)", min_value=0.1, max_value=2.0, value=0.5, step=0.1)
        contour_major = sc3.slider("Major contour (m)", min_value=0.5, max_value=10.0, value=1.0, step=0.5)
        allow_coarsen = st.checkbox(
            "Auto-coarsen grid on very large sites (faster, lower resolution)",
            value=False,
            help="Off (default): keep requested spacing (e.g. 5 m) up to ~1.5M grid points — "
                 "best for layout. On: may increase spacing on huge boundaries to speed up the run.",
        )
        help_caption("glo30", "grid_spacing")

        _site_area_ha = boundaries_union_area_ha(_enabled_polys) if _enabled_polys else None
        _area_over_limit = (
            _site_area_ha is not None and _site_area_ha > MAX_SITE_AREA_HA
        )
        if _area_over_limit:
            st.error(_area_limit_message(_site_area_ha))

        _topo_user = st.session_state.get("pvm_user_id", "guest")
        _topo_left = remaining(_topo_user, "topoiq")

        if is_over_limit(_topo_user, "topoiq"):
            show_paywall("TopoIQ")
        else:
            if _topo_left <= 1:
                st.warning(f"⚠️ {_topo_left} free analysis remaining after this run.")
            run = st.button("⛰ Run Terrain Analysis", type="primary",
                            use_container_width=True,
                            disabled=(not _enabled_polys or _area_over_limit))
            st.caption(
                "After running, **download your exports immediately** — files are not stored. "
                "Leaving this page or changing settings requires a new run."
            )
            if not _enabled_polys:
                if st.session_state.get("topo_analysis_mode") == "drawn":
                    st.caption("Draw your analysis boundary on the map above.")
                else:
                    st.caption("Enable at least one parcel in **Project Setup** and save the project.")
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

        with st.spinner(f"Processing {grid_spacing} m grid…"):
            try:
                X, Y, Z, grid_m_used = resample_to_grid(
                    mosaic, lat_n, lat_s, lon_w, lon_e,
                    polygon_list=_enabled_polys, grid_m=float(grid_spacing),
                    allow_coarsen=allow_coarsen,
                )
            except ValueError as exc:
                if str(exc) == "GRID_TOO_LARGE":
                    st.error(
                        f"This boundary is too large for a **{grid_spacing} m** grid at full resolution. "
                        "Enable **Auto-coarsen grid** above, reduce enabled parcels, draw a smaller "
                        "analysis polygon, or increase grid spacing."
                    )
                    st.stop()
                raise
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
            st.warning(
                f"Grid coarsened to **{grid_m_used:.0f} m** "
                f"(requested {grid_spacing:.0f} m) — auto-coarsen is enabled for this large boundary."
            )
        if dem_zoom < DEM_ZOOM_MAX:
            st.caption(
                f"DEM fetched at zoom **{dem_zoom}** "
                f"({tile_count_for_bbox(south, north, west, east, dem_zoom)} tiles) "
                f"for this site size — resampled to your output grid."
            )

        m1, m2, m3, m4 = st.columns(4)
        metrics = [
            ("fa-arrow-down", "#e53935", "Min Elevation", f"{round(z_valid.min())} m"),
            ("fa-arrow-up",   "#43a047", "Max Elevation", f"{round(z_valid.max())} m"),
            ("fa-wave-square","#1565c0", "Elev Range",    f"{round(z_valid.max()-z_valid.min())} m"),
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
        ha_over10 = area_ha * pct_over10 / 100.0
        _n_slope = len(s_valid)
        _slope_bins = (
            float((s_valid <= 2.5).sum() / _n_slope * 100),
            float(((s_valid > 2.5) & (s_valid <= 5)).sum() / _n_slope * 100),
            float(((s_valid > 5) & (s_valid <= 7.5)).sum() / _n_slope * 100),
            float(((s_valid > 7.5) & (s_valid <= 10)).sum() / _n_slope * 100),
            float((s_valid > 10).sum() / _n_slope * 100),
        ) if _n_slope else None

        _siq_cache = st.session_state.get("siteiq_run_cache") or {}
        _land_use = _siq_cache.get("land_use", "Standard")
        _extras = compute_terrain_extras(X, Y, Z, grid_m_used)

        _topo_cache = build_topo_cache(
            project_row_id=st.session_state.get("pvm_project_row_id"),
            analysis_mode=st.session_state.get("topo_analysis_mode", "parcels"),
            boundary_fp=fingerprint_from_latlon_polys(_enabled_polys),
            area_ha=area_ha,
            lat_c=lat_c,
            lon_c=lon_c,
            grid_m=grid_m_used,
            grid_points=len(z_valid),
            mean_slope=mean_slope,
            max_slope=float(s_valid.max()),
            pct_over5=pct_over5,
            pct_over10=pct_over10,
            z_min=float(z_valid.min()),
            z_max=float(z_valid.max()),
            center_elev=float(z_valid.mean()),
            extras=_extras,
            dem_zoom=dem_zoom,
        )
        persist_topo_cache(
            _topo_cache,
            st.session_state,
            user_id=st.session_state.get("pvm_user_id", ""),
            save_fn=save_project,
        )

        _vf_label, _vf_detail = verdict_for_mount(mean_slope, "Fixed Tilt")
        _vt_label, _vt_detail = verdict_for_mount(
            mean_slope, "Single-Axis Tracker", extras=_extras,
        )

        vc1, vc2 = st.columns(2)
        with vc1:
            st.success(f"**Fixed Tilt:** {_vf_label} — {_vf_detail}")
        with vc2:
            _vt_style = st.success if "Excellent" in _vt_label and "Review" not in _vt_label else st.warning
            _vt_style(f"**Tracker:** {_vt_label} — {_vt_detail}")

        _tds = compute_terrain_drivers_summary(
            mean_slope, float(s_valid.max()), _slope_bins, _extras,
            (_vf_label, _vf_detail), (_vt_label, _vt_detail),
        )
        _driver_rows = ""
        for _drv, _imp, _kind in _tds["drivers"]:
            if _kind == "positive":
                _imp_html = f'<span style="color:#1b5e20;font-weight:600;">✓ {_imp}</span>'
            elif _kind == "warn":
                _imp_html = f'<span style="color:#c65d00;font-weight:600;">⚠ {_imp}</span>'
            else:
                _imp_html = f'<span style="color:#555;">{_imp}</span>'
            _driver_rows += (
                f'<tr>'
                f'<td style="padding:0.45rem 0.6rem;border-bottom:1px solid #e8edf2;">{_drv}</td>'
                f'<td style="padding:0.45rem 0.6rem;border-bottom:1px solid #e8edf2;">{_imp_html}</td>'
                f'</tr>'
            )
        _why_items = ""
        for _wk, _wt in _tds["why_bullets"]:
            if _wk == "positive":
                _why_items += (
                    f'<li style="margin:0.35rem 0;color:#1a3a2a;">'
                    f'<span style="color:#1b5e20;font-weight:700;">✓</span> {_wt}</li>'
                )
            else:
                _why_items += (
                    f'<li style="margin:0.35rem 0;color:#4a3a2a;">'
                    f'<span style="color:#c65d00;font-weight:700;">⚠</span> {_wt}</li>'
                )
        st.markdown(
            f'<div style="background:#f0f4f8;border:1px solid #c5d4e3;border-radius:10px;'
            f'padding:0.9rem 1rem;margin:0.75rem 0;">'
            f'<div style="font-size:0.72rem;font-weight:800;text-transform:uppercase;'
            f'letter-spacing:0.1em;color:#1565c0;margin-bottom:0.4rem;">Terrain Drivers</div>'
            f'<div style="font-size:1.2rem;font-weight:800;color:#0d2137;margin-bottom:0.65rem;">'
            f'Terrain Score: {_tds["terrain_score"]}/100 '
            f'<span style="font-size:0.95rem;color:#1565c0;">'
            f'({_tds["terrain_score_label"]})</span></div>'
            f'<table style="width:100%;border-collapse:collapse;font-size:0.84rem;margin-bottom:0.75rem;">'
            f'<thead><tr style="background:#1565c0;color:#fff;">'
            f'<th style="padding:0.45rem 0.6rem;text-align:left;font-weight:700;">Driver</th>'
            f'<th style="padding:0.45rem 0.6rem;text-align:left;font-weight:700;">Impact</th>'
            f'</tr></thead><tbody>{_driver_rows}</tbody></table>'
            f'<div style="font-size:0.82rem;font-weight:700;color:#0d2137;margin-bottom:0.35rem;">'
            f'Why this verdict?</div>'
            f'<ul style="margin:0;padding-left:1.1rem;font-size:0.82rem;">{_why_items}</ul>'
            f'</div>',
            unsafe_allow_html=True,
        )
        help_caption("terrain_score", "terrain_verdict")

        _ft_band = capacity_band(area_ha, _land_use, "Fixed Tilt")
        _tr_band = capacity_band(area_ha, _land_use, "Single-Axis Tracker")
        st.caption(
            f"Indicative DC capacity — "
            f"Fixed tilt {format_mwp_range(_ft_band['mwp_lo'], _ft_band['mwp_hi'])} · "
            f"Tracker {format_mwp_range(_tr_band['mwp_lo'], _tr_band['mwp_hi'])} "
            f"@ GCR {GCR_SCREEN_LO:.2f}–{GCR_SCREEN_HI:.2f} (1P screening). "
            f"{capacity_footnote_global()}"
        )
        st.caption(module_confidence_label("topoiq"))

        with st.spinner("Fetching cross-module yield reference…"):
            _yield_xref = fetch_yield_cross_ref_bundle(lat_c, lon_c)
        _yield_xref_txt = yield_cross_ref_topoiq_text(_yield_xref)
        if _yield_xref_txt:
            st.markdown(yield_cross_ref_topoiq_html(_yield_xref), unsafe_allow_html=True)

        if _extras.get("cross_row_mean") is not None:
            st.caption(
                f"Cross-row slope (tracker screening): mean **{_extras['cross_row_mean']:.1f}%** · "
                f"95th %ile **{_extras['cross_row_p95']:.1f}%**"
            )
            help_caption("cross_row_slope")

        st.markdown(
            f'<div style="font-size:1rem;font-weight:600;color:#1a1a1a;'
            f'background:#f0f4f8;border-radius:8px;padding:0.55rem 1rem;margin-top:0.3rem;">'
            f'📐 <b>{area_ha:.1f} ha</b> &nbsp;·&nbsp; '
            f'🔢 <b>{len(z_valid):,}</b> points at <b>{grid_m_used:.0f} m</b> output grid &nbsp;·&nbsp; '
            f'<span style="font-size:0.85em;color:#555;">GLO-30 native ~30 m</span> &nbsp;·&nbsp; '
            f'⚠️ <b>{pct_over5:.1f}%</b> (&gt;5% slope) &nbsp;·&nbsp; '
            f'🔴 <b>{pct_over10:.1f}%</b> (&gt;10%, ≈{ha_over10:.1f} ha) · max point <b>{s_valid.max():.1f}%</b>'
            f'</div>',
            unsafe_allow_html=True
        )
        help_caption("mean_slope", "max_slope", "screening_grade")

        st.divider()
        st.markdown('<div class="section-hdr"><i class="fa-solid fa-layer-group" style="color:#1565c0;"></i> Slope Map</div>', unsafe_allow_html=True)

        pdf_slope_buf = None
        if HAS_SCIPY:
            with st.spinner("Rendering slope map…"):
                pdf_slope_buf = render_slope_map_png(
                    X, Y, Z, grid_m_used, south, north, west, east,
                    polygon_list=_enabled_polys,
                )
            if pdf_slope_buf:
                st.image(pdf_slope_buf, use_container_width=True)
                pdf_slope_buf.seek(0)
            st.caption(
                "Slope over satellite basemap — green = flat (<3%), red = steep (>10%). "
                "North arrow and scale bar included in PDF export."
            )
        else:
            st.info("Install scipy for slope maps.")

        st.divider()
        st.markdown('<div class="section-hdr"><i class="fa-solid fa-download" style="color:#1565c0;"></i> Download Outputs</div>', unsafe_allow_html=True)
        st.caption(
            "**From KMZ to CAD:** UTM surface, contours, and parcel linework — screening-grade, not survey."
        )
        help_caption("cad_export", "screening_grade")

        _export_base = sanitize_topo_basename(_proj.get("name", ""))
        _cad_units = export_linear_units(_proj.get("country", ""))
        _unit_label = "US Survey Feet" if _cad_units == "imperial_us_survey" else "meters"
        _ref_elev = float(z_valid.mean())
        _ref_epsg = epsg_utm_wgs84(lat_c, lon_c)
        _ref_utm_e, _ref_utm_n, _ = latlon_to_utm(lat_c, lon_c)
        _parcel_count = len(_enabled_polys)

        st.info(
            f"**Reference point:** boundary centroid at {format_coords(lat_c, lon_c)} "
            f"(EPSG:{_ref_epsg} UTM). Local CAD exports use **(0, 0)** at this point. "
            f"Georef exports use **{_unit_label}**. "
            f"Parcel linework is on layer **SITE_BOUNDARY** in the DXF files and in LandXML (Parcels). "
            f"See `{_export_base}_reference.json` in the ZIP."
        )
        if _cad_units == "imperial_us_survey":
            st.caption(
                "USA project: import georef LandXML/DXF into an **imperial CAD drawing** — "
                "coordinates are already in US Survey Feet. Do not apply extra feet↔meter scaling."
            )
        if _parcel_count > 1:
            st.warning(
                f"**{_parcel_count} enabled parcels** — one merged LandXML surface is exported. "
                "Gaps between separate parcels may show as TIN breaklines in CAD. "
                "For a seamless surface, use one continuous boundary (draw custom or merge in KMZ)."
            )

        with st.spinner("Generating PDF report…"):
            _slope_pdf = io.BytesIO(pdf_slope_buf.getvalue()) if pdf_slope_buf else None
            _ctx = build_report_context(
                project_name=_proj.get("name", ""),
                country=_proj.get("country", ""),
                location_label=resolve_location_label(
                    lat_c, lon_c,
                    saved_label=_proj.get("location_label", ""),
                    country=_proj.get("country", ""),
                ),
                lat_c=lat_c, lon_c=lon_c,
                area_ha=area_ha, grid_spacing=grid_m_used,
                grid_spacing_requested=float(grid_spacing),
                z_min=float(z_valid.min()), z_max=float(z_valid.max()),
                mean_slope=mean_slope, max_slope=float(s_valid.max()),
                pct_over5=pct_over5, pct_over10=pct_over10,
                slope_bins=_slope_bins,
                slope_img_buf=_slope_pdf,
                land_use=_land_use,
                mount_type=None,
                boundary_provenance=_boundary_provenance(_boundaries, _proj),
                prepared_by=prepared_by_line(),
                module_confidence=module_confidence_label("topoiq"),
                extras=_extras,
                siteiq_run_cache=st.session_state.get("siteiq_run_cache"),
                project_row_id=st.session_state.get("pvm_project_row_id"),
                dem_zoom=dem_zoom,
                yield_cross_ref=_yield_xref_txt,
            )
            pdf_bytes = generate_pdf_report(_ctx)
        if pdf_bytes:
            st.download_button(
                "📄 Download Terrain Report (PDF)",
                pdf_bytes,
                file_name=f"{_export_base}_report.pdf",
                mime="application/pdf",
                use_container_width=True,
                type="primary",
                help="Full terrain report with maps, metrics and engineering verdict"
            )
            st.divider()

        with st.spinner("Preparing export files…"):
            _e_local, _n_local = local_en_from_latlon(X, Y, lon_c, lat_c)
            _e_georef, _n_georef, _ = utm_grids_from_latlon(X, Y, lat_c, lon_c)

            lxml = export_landxml_utm(
                X, Y, Z, site_name=_export_base, lat_c=lat_c, lon_c=lon_c,
                polygon_list=_enabled_polys, units=_cad_units,
            )
            xyz_local = export_xyz_local(X, Y, Z, lat_c, lon_c, units=_cad_units)
            xyz_georef = export_xyz_georef(X, Y, Z, lat_c, lon_c, units=_cad_units)
            xyz_geo = export_xyz_geo(X, Y, Z)
            reference_json = build_reference_json(
                project_name=_proj.get("name", ""),
                lat_c=lat_c,
                lon_c=lon_c,
                elev_c=_ref_elev,
                grid_m=grid_m_used,
                epsg=_ref_epsg,
                utm_e=_ref_utm_e,
                utm_n=_ref_utm_n,
                parcel_count=_parcel_count,
                analysis_mode=st.session_state.get("topo_analysis_mode", "parcels"),
                country=_proj.get("country", ""),
                linear_units=_cad_units,
            )
            dxf_local = None
            dxf_georef = None
            if HAS_EZDXF:
                dxf_local = export_dxf_contours(
                    X, Y, Z,
                    easting=_e_local, northing=_n_local,
                    polygon_list=_enabled_polys,
                    lat_c=lat_c, lon_c=lon_c,
                    minor_int=contour_minor,
                    major_int=contour_major,
                    georef=False,
                    units=_cad_units,
                )
                dxf_georef = export_dxf_contours(
                    X, Y, Z,
                    easting=_e_georef, northing=_n_georef,
                    polygon_list=_enabled_polys,
                    lat_c=lat_c, lon_c=lon_c,
                    minor_int=contour_minor,
                    major_int=contour_major,
                    georef=True,
                    units=_cad_units,
                )

        _zip_bytes, _zip_files = build_topo_export_zip(
            _export_base,
            pdf_bytes=pdf_bytes,
            reference_json=reference_json,
            lxml=lxml,
            xyz_local=xyz_local,
            xyz_georef=xyz_georef,
            xyz_geo=xyz_geo,
            dxf_local=dxf_local,
            dxf_georef=dxf_georef,
        )
        if _zip_bytes:
            _zip_label = ", ".join(_zip_files)
            st.download_button(
                "📦 Download All (ZIP)",
                _zip_bytes,
                file_name=f"{_export_base}_exports.zip",
                mime="application/zip",
                use_container_width=True,
                type="primary",
                help=f"One ZIP with all exports: {_zip_label}",
            )
            st.caption(f"Includes: {_zip_label}")

        ex1, ex2, ex3 = st.columns(3)
        ex4, ex5, ex6 = st.columns(3)

        if lxml:
            ex1.download_button("⬇ LandXML (UTM)", lxml,
                                file_name=f"{_export_base}.xml",
                                mime="application/xml",
                                use_container_width=True,
                                help="Merged TIN + parcel linework (Parcels/PlanFeatures) in WGS84 UTM")

        if dxf_local:
            ex2.download_button("⬇ DXF Local", dxf_local,
                                file_name=f"{_export_base}_contours_local.dxf",
                                mime="application/dxf",
                                use_container_width=True,
                                help="Contours + SITE_BOUNDARY parcel linework at centroid origin (0,0)")
        elif not HAS_EZDXF:
            ex2.info("Install ezdxf for DXF export")

        if dxf_georef:
            ex3.download_button("⬇ DXF Georef", dxf_georef,
                                file_name=f"{_export_base}_contours_georef.dxf",
                                mime="application/dxf",
                                use_container_width=True,
                                help="Contours + SITE_BOUNDARY parcel linework in WGS84 UTM meters")

        ex4.download_button("⬇ XYZ Local", xyz_local,
                            file_name=f"{_export_base}_local.csv",
                            mime="text/csv",
                            use_container_width=True,
                            help="Easting/Northing/Elevation from centroid (m)")

        ex5.download_button("⬇ XYZ Georef", xyz_georef,
                            file_name=f"{_export_base}_georef.csv",
                            mime="text/csv",
                            use_container_width=True,
                            help="UTM Easting/Northing/Elevation (m)")

        ex6.download_button("⬇ Geo CSV", xyz_geo,
                            file_name=f"{_export_base}_geo.csv",
                            mime="text/csv",
                            use_container_width=True,
                            help="Lon/Lat/Elevation for GIS or PVsyst — not the primary CAD surface path")

        st.markdown(f"""
        <div class="accuracy-card">
          <h4><i class="fa-solid fa-circle-info" style="margin-right:0.3rem;"></i> Data Source & Accuracy</h4>
          <p><strong>Source:</strong> Copernicus DEM GLO-30 (ESA/EC, 2021) via AWS Terrain Tiles</p>
          <p><strong>Native resolution:</strong> ~30 m horizontal (GLO-30); tiles at zoom {dem_zoom}</p>
          <p><strong>Output grid:</strong> {grid_m_used:.0f} m — resampled for layout/CAD (default 5 m; not survey-grade feature detail)</p>
          <p><strong>Vertical accuracy:</strong> ±1–3 m RMSE typical (better on open ground; worse in dense vegetation)</p>
          <p><strong>Recommendation:</strong> Screening-grade terrain assessment only. Verify critical slopes and grades with LiDAR or RTK survey before FEED and pile layout.</p>
          <p style="color:#e53935;margin-top:0.4rem;">
            <i class="fa-solid fa-triangle-exclamation"></i>
            Dense vegetation (forests) and urban areas may cause elevation overestimation.
            Check against site photos before final use.
          </p>
        </div>
        """, unsafe_allow_html=True)

    else:
        st.caption("Set up your site boundary in **Project Setup**, then run terrain analysis on the left.")
        wc1, wc2 = st.columns(2)
        _wcards = [
            (wc1, "Satellite DEM",
             "Copernicus GLO-30 · ~30 m native · resampled to 5 m for layout"),
            (wc2, "CAD package",
             "UTM LandXML surface, DXF contours & parcel linework from your KMZ"),
            (wc1, "DXF + LandXML",
             "Contours with parcel linework on SITE_BOUNDARY · local or UTM"),
            (wc2, "XYZ point cloud",
             "Easting / Northing / Elevation CSV for any tool"),
            (wc1, "Slope analysis",
             "Mean slope · % area over threshold · tracker suitability"),
            (wc2, "Accuracy report",
             "Source · resolution · RMSE · vegetation warnings"),
        ]
        for _col, _title, _desc in _wcards:
            _col.markdown(
                f'<div class="topo-feature-card">'
                f'<div class="topo-feature-title">{_title}</div>'
                f'<div class="topo-feature-desc">{_desc}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
