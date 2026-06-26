"""Framework-agnostic TopoIQ terrain engine shared by API and Streamlit."""

from __future__ import annotations

import concurrent.futures
import io
import math
import os
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import requests
from PIL import Image

from pvmath_terrain_report import (
    compute_terrain_drivers_summary,
    compute_terrain_extras,
    verdict_for_mount,
)
from pvmath_terrain_sources import route_payload, select_terrain_route

try:
    from scipy.ndimage import gaussian_filter

    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    from shapely.geometry import Polygon as ShapelyPolygon
    from shapely.geometry import shape as shapely_shape
    from shapely.ops import unary_union
    from shapely.vectorized import contains as shp_contains

    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False


def _geojson_to_shapely(geojson: Any):
    """Best-effort GeoJSON (geometry / Feature / FeatureCollection) → shapely."""
    if not geojson or not HAS_SHAPELY:
        return None
    try:
        gtype = geojson.get("type")
        if gtype == "FeatureCollection":
            geoms = [
                _geojson_to_shapely(f.get("geometry"))
                for f in geojson.get("features", [])
            ]
            geoms = [g for g in geoms if g is not None and not g.is_empty]
            return unary_union(geoms) if geoms else None
        if gtype == "Feature":
            return _geojson_to_shapely(geojson.get("geometry"))
        geom = shapely_shape(geojson)
        if geom.is_empty:
            return None
        if not geom.is_valid:
            geom = geom.buffer(0)
        return geom
    except Exception:
        return None


MAX_SITE_AREA_HA = 10_000
MAX_DEM_TILES = 80
MAX_GRID_POINTS_LAYOUT = 1_500_000
MAX_GRID_POINTS_FAST = 300_000
DEM_ZOOM_MIN = 11
DEM_ZOOM_MAX = 14
TILE_FETCH_WORKERS = 8
TILE_PX = 256


def deg2tile(lat: float, lon: float, zoom: int) -> Tuple[int, int]:
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int(
        (1.0 - math.log(math.tan(math.radians(lat)) + 1.0 / math.cos(math.radians(lat))) / math.pi)
        / 2.0
        * n
    )
    return x, y


def tile2deg(x: int, y: int, zoom: int) -> Tuple[float, float]:
    n = 2 ** zoom
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lat, lon


def _tile_url_for_source(terrain_source: str, zoom: int, x: int, y: int) -> str:
    source = (terrain_source or "").strip().lower()
    env_key = {
        "copernicus_eea10": "PVMATH_EEA10_TILE_URL",
        "fabdem": "PVMATH_FABDEM_TILE_URL",
    }.get(source)
    if env_key:
        tpl = (os.environ.get(env_key) or "").strip()
        if tpl:
            return tpl.format(z=zoom, x=x, y=y)
    return f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{zoom}/{x}/{y}.png"


def fetch_terrarium_tile(
    x: int,
    y: int,
    zoom: int,
    terrain_source: str = "copernicus_glo30",
) -> Tuple[Optional[np.ndarray], Dict[str, float]]:
    lat_n, lon_w = tile2deg(x, y, zoom)
    lat_s, lon_e = tile2deg(x + 1, y + 1, zoom)
    bounds = {"lat_n": lat_n, "lat_s": lat_s, "lon_w": lon_w, "lon_e": lon_e}
    url = _tile_url_for_source(terrain_source, zoom, x, y)
    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            return None, bounds
        img = Image.open(io.BytesIO(response.content)).convert("RGB")
        if img.size != (TILE_PX, TILE_PX):
            return None, bounds
        arr = np.array(img, dtype=np.float32)
        elev = arr[:, :, 0] * 256.0 + arr[:, :, 1] + arr[:, :, 2] / 256.0 - 32768.0
        elev = np.where((elev < -500) | (elev > 9000), np.nan, elev)
        return elev, bounds
    except Exception:
        return None, bounds


def tile_count_for_bbox(south: float, north: float, west: float, east: float, zoom: int) -> int:
    x_min, y_min = deg2tile(north, west, zoom)
    x_max, y_max = deg2tile(south, east, zoom)
    return (x_max - x_min + 1) * (y_max - y_min + 1)


def pick_dem_zoom(
    south: float,
    north: float,
    west: float,
    east: float,
    max_tiles: int = MAX_DEM_TILES,
) -> int:
    for zoom in range(DEM_ZOOM_MAX, DEM_ZOOM_MIN - 1, -1):
        if tile_count_for_bbox(south, north, west, east, zoom) <= max_tiles:
            return zoom
    return DEM_ZOOM_MIN


def get_dem_for_bbox(
    south: float,
    north: float,
    west: float,
    east: float,
    zoom: int = DEM_ZOOM_MAX,
    terrain_source: str = "copernicus_glo30",
    progress_cb: Optional[Callable[[float, str], None]] = None,
) -> Tuple[Optional[np.ndarray], Optional[float], Optional[float], Optional[float], Optional[float]]:
    x_min, y_min = deg2tile(north, west, zoom)
    x_max, y_max = deg2tile(south, east, zoom)
    tile_list = [(tx, ty) for ty in range(y_min, y_max + 1) for tx in range(x_min, x_max + 1)]
    total = len(tile_list)
    fetched: Dict[Tuple[int, int], Tuple[Optional[np.ndarray], Dict[str, float]]] = {}
    any_success = False
    done = 0

    if progress_cb:
        progress_cb(0.0, "Downloading terrain tiles")

    def _fetch_one(tx_ty: Tuple[int, int]):
        tx, ty = tx_ty
        return tx_ty, fetch_terrarium_tile(tx, ty, zoom, terrain_source=terrain_source)

    with concurrent.futures.ThreadPoolExecutor(max_workers=TILE_FETCH_WORKERS) as executor:
        futures = [executor.submit(_fetch_one, t) for t in tile_list]
        for future in concurrent.futures.as_completed(futures):
            (tx, ty), (elev, bounds) = future.result()
            fetched[(tx, ty)] = (elev, bounds)
            if elev is not None:
                any_success = True
            done += 1
            if progress_cb and total:
                progress_cb(done / total, f"Downloading tile {done}/{total}")

    if progress_cb:
        progress_cb(1.0, "Terrain tile download complete")

    if not any_success:
        return None, None, None, None, None

    tile_rows = []
    bounds_grid = []
    for ty in range(y_min, y_max + 1):
        row_imgs = []
        row_bounds = []
        for tx in range(x_min, x_max + 1):
            elev, bounds = fetched[(tx, ty)]
            if elev is None:
                elev = np.full((TILE_PX, TILE_PX), np.nan, dtype=np.float32)
            row_imgs.append(elev)
            row_bounds.append(bounds)
        tile_rows.append(row_imgs)
        bounds_grid.append(row_bounds)

    mosaic = np.concatenate([np.concatenate(row, axis=1) for row in tile_rows], axis=0)
    lat_n_all = bounds_grid[0][0]["lat_n"]
    lat_s_all = bounds_grid[-1][0]["lat_s"]
    lon_w_all = bounds_grid[0][0]["lon_w"]
    lon_e_all = bounds_grid[0][-1]["lon_e"]
    return mosaic, lat_n_all, lat_s_all, lon_w_all, lon_e_all


def effective_grid_spacing(
    p_w: float,
    p_e: float,
    p_s: float,
    p_n: float,
    grid_m: float,
    lat_c: float,
    allow_coarsen: bool = False,
) -> Optional[float]:
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


def _polygon_mask(X: np.ndarray, Y: np.ndarray, polygon_coords: Sequence[Tuple[float, float]]) -> np.ndarray:
    if not polygon_coords or len(polygon_coords) < 3:
        return np.ones(X.shape, dtype=bool)
    if HAS_SHAPELY:
        return shp_contains(ShapelyPolygon(polygon_coords), X, Y)
    from matplotlib.path import Path

    pts = np.column_stack([X.ravel(), Y.ravel()])
    return Path(polygon_coords).contains_points(pts).reshape(X.shape)


def _polygons_mask(
    X: np.ndarray,
    Y: np.ndarray,
    polygon_list: Sequence[Sequence[Tuple[float, float]]],
) -> np.ndarray:
    if not polygon_list:
        return np.ones(X.shape, dtype=bool)
    mask = np.zeros(X.shape, dtype=bool)
    for coords in polygon_list:
        if coords and len(coords) >= 3:
            mask |= _polygon_mask(X, Y, coords)
    return mask


def resample_to_grid(
    mosaic: np.ndarray,
    lat_n: float,
    lat_s: float,
    lon_w: float,
    lon_e: float,
    polygon_coords: Optional[Sequence[Tuple[float, float]]] = None,
    polygon_list: Optional[Sequence[Sequence[Tuple[float, float]]]] = None,
    grid_m: float = 5.0,
    allow_coarsen: bool = False,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    h, w = mosaic.shape
    lat_c = (lat_n + lat_s) / 2
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat_c))

    polys = list(polygon_list) if polygon_list else ([polygon_coords] if polygon_coords else [])
    if polys:
        all_lons = [c[0] for p in polys for c in p]
        all_lats = [c[1] for p in polys for c in p]
        p_w, p_e = min(all_lons), max(all_lons)
        p_s, p_n = min(all_lats), max(all_lats)
    else:
        p_w, p_e, p_s, p_n = lon_w, lon_e, lat_s, lat_n

    grid_m_used = effective_grid_spacing(
        p_w,
        p_e,
        p_s,
        p_n,
        grid_m,
        lat_c,
        allow_coarsen=allow_coarsen,
    )
    if grid_m_used is None:
        raise ValueError("GRID_TOO_LARGE")

    step_lat = grid_m_used / m_per_deg_lat
    step_lon = grid_m_used / m_per_deg_lon
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
    return X, Y, Z, float(grid_m_used)


def compute_slope(Z: np.ndarray, grid_m: float) -> np.ndarray:
    Zf = gaussian_filter(Z.astype(float), sigma=1) if HAS_SCIPY else Z.astype(float)
    dz_dy, dz_dx = np.gradient(Zf, grid_m)
    return np.sqrt(dz_dx**2 + dz_dy**2) * 100.0


def boundary_area_ha(polygon_coords: Sequence[Tuple[float, float]]) -> float:
    if not polygon_coords or len(polygon_coords) < 3:
        return 0.0
    lats = [c[1] for c in polygon_coords]
    mean_lat = sum(lats) / len(lats)
    lat_m = 111320.0
    lon_m = 111320.0 * math.cos(math.radians(mean_lat))
    pts = [(c[0] * lon_m, c[1] * lat_m) for c in polygon_coords]
    area = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        area += x1 * y2 - x2 * y1
    return round(abs(area) * 0.5 / 10_000, 2)


def boundaries_union_area_ha(polygon_list: Sequence[Sequence[Tuple[float, float]]]) -> float:
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
            return round(unary_union(shapes).area / 10_000, 2)
        except Exception:
            pass
    return round(sum(boundary_area_ha(p) for p in polys), 2)


def run_topo_analysis(
    polygons: Sequence[Sequence[Tuple[float, float]]],
    grid_m: float = 5.0,
    allow_coarsen: bool = False,
    contour_minor: float = 0.5,
    contour_major: float = 1.0,
    progress_cb: Optional[Callable[[float, str], None]] = None,
    mask_geojson: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    enabled_polys = [list(poly) for poly in polygons if poly and len(poly) >= 3]
    if not enabled_polys:
        raise ValueError("NO_BOUNDARY")

    lons_p = [c[0] for poly in enabled_polys for c in poly]
    lats_p = [c[1] for poly in enabled_polys for c in poly]
    south, north = min(lats_p) - 0.001, max(lats_p) + 0.001
    west, east = min(lons_p) - 0.001, max(lons_p) + 0.001
    lat_c = (south + north) / 2
    lon_c = (west + east) / 2
    area_ha = boundaries_union_area_ha(enabled_polys)

    terrain_route = select_terrain_route(lat_c, lon_c)
    terrain_meta = route_payload(terrain_route)
    terrain_source_used = terrain_meta["source"]
    dem_zoom = pick_dem_zoom(south, north, west, east)

    mosaic, lat_n, lat_s, lon_w, lon_e = get_dem_for_bbox(
        south,
        north,
        west,
        east,
        zoom=dem_zoom,
        terrain_source=terrain_source_used,
        progress_cb=progress_cb,
    )
    if mosaic is None:
        raise RuntimeError("DEM_FETCH_FAILED")

    X, Y, Z, grid_m_used = resample_to_grid(
        mosaic,
        lat_n,
        lat_s,
        lon_w,
        lon_e,
        polygon_list=enabled_polys,
        grid_m=float(grid_m),
        allow_coarsen=allow_coarsen,
    )

    # Restrict analysis to the SiteIQ buildable area when supplied: cells outside
    # the buildable geometry (e.g. building/road setback "red zones") become NaN
    # so slope stats and the slope map reflect only buildable land.
    if mask_geojson is not None and HAS_SHAPELY:
        buildable = _geojson_to_shapely(mask_geojson)
        if buildable is not None and not buildable.is_empty:
            inside = shp_contains(buildable, X, Y)
            if inside.any():
                Z = np.where(inside, Z, np.nan)

    slope = compute_slope(Z, grid_m_used)

    if X.shape[0] < 2 or X.shape[1] < 2:
        raise RuntimeError("GRID_TOO_SMALL")

    z_valid = Z[~np.isnan(Z)]
    s_valid = slope[~np.isnan(slope) & ~np.isnan(Z)]
    if len(z_valid) == 0 or len(s_valid) == 0:
        raise RuntimeError("NO_DATA_IN_BOUNDARY")

    mean_slope = float(s_valid.mean())
    max_slope = float(s_valid.max())
    pct_over5 = float((s_valid > 5).sum() / len(s_valid) * 100)
    pct_over10 = float((s_valid > 10).sum() / len(s_valid) * 100)
    n_slope = len(s_valid)
    slope_bins: Optional[Tuple[float, float, float, float, float]] = None
    if n_slope:
        slope_bins = (
            float((s_valid <= 2.5).sum() / n_slope * 100),
            float(((s_valid > 2.5) & (s_valid <= 5)).sum() / n_slope * 100),
            float(((s_valid > 5) & (s_valid <= 7.5)).sum() / n_slope * 100),
            float(((s_valid > 7.5) & (s_valid <= 10)).sum() / n_slope * 100),
            float((s_valid > 10).sum() / n_slope * 100),
        )

    extras = compute_terrain_extras(X, Y, Z, grid_m_used)
    verdict_fixed = verdict_for_mount(mean_slope, "Fixed Tilt")
    verdict_tracker = verdict_for_mount(mean_slope, "Single-Axis Tracker", extras=extras)
    terrain_drivers = compute_terrain_drivers_summary(
        mean_slope,
        max_slope,
        slope_bins,
        extras,
        verdict_fixed,
        verdict_tracker,
    )

    return {
        "bbox": {
            "south": south,
            "north": north,
            "west": west,
            "east": east,
            "lat_c": lat_c,
            "lon_c": lon_c,
        },
        "area_ha": area_ha,
        "grid_m_requested": float(grid_m),
        "grid_m_used": float(grid_m_used),
        "grid_points": int(len(z_valid)),
        "dem_zoom": int(dem_zoom),
        "tile_count": int(tile_count_for_bbox(south, north, west, east, dem_zoom)),
        "terrain_source_used": terrain_source_used,
        "terrain_source": terrain_meta,
        "elevation": {
            "z_min": float(z_valid.min()),
            "z_max": float(z_valid.max()),
            "z_range": float(z_valid.max() - z_valid.min()),
            "center_elev": float(z_valid.mean()),
        },
        "slope": {
            "mean": mean_slope,
            "max": max_slope,
            "pct_over5": pct_over5,
            "pct_over10": pct_over10,
            "bins": slope_bins,
        },
        "extras": extras,
        "verdict_fixed": {"label": verdict_fixed[0], "detail": verdict_fixed[1]},
        "verdict_tracker": {"label": verdict_tracker[0], "detail": verdict_tracker[1]},
        "terrain_drivers": terrain_drivers,
        "contours": {
            "minor_m": float(contour_minor),
            "major_m": float(contour_major),
        },
        "X": X,
        "Y": Y,
        "Z": Z,
        "slope_grid": slope,
        "polygons": enabled_polys,
    }
