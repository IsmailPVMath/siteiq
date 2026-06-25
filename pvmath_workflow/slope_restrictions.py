"""Generate no-build polygons from TopoIQ slope rasters."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from pvmath_topo_engine import boundaries_union_area_ha, run_topo_analysis


def _site_union(polygons: Sequence[Sequence[Tuple[float, float]]]):
    geoms = []
    for poly in polygons:
        if not poly or len(poly) < 3:
            continue
        geom = Polygon(poly)
        if not geom.is_valid:
            geom = geom.buffer(0)
        if not geom.is_empty:
            geoms.append(geom)
    if not geoms:
        return None
    return unary_union(geoms)


def _cell_half_steps(X: np.ndarray, Y: np.ndarray, row: int, col: int) -> tuple[float, float]:
    cols = X.shape[1]
    rows = Y.shape[0]
    if cols > 1:
        if col == 0:
            dx = abs(float(X[row, col + 1] - X[row, col]))
        elif col == cols - 1:
            dx = abs(float(X[row, col] - X[row, col - 1]))
        else:
            dx = abs(float(X[row, col + 1] - X[row, col - 1])) / 2.0
    else:
        dx = 1e-5
    if rows > 1:
        if row == 0:
            dy = abs(float(Y[row + 1, col] - Y[row, col]))
        elif row == rows - 1:
            dy = abs(float(Y[row, col] - Y[row - 1, col]))
        else:
            dy = abs(float(Y[row + 1, col] - Y[row - 1, col])) / 2.0
    else:
        dy = 1e-5
    return dx / 2.0, dy / 2.0


def _rings_from_geom(geom) -> List[List[List[float]]]:
    if geom.is_empty:
        return []
    geoms = [geom] if geom.geom_type == "Polygon" else [
        g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon"
    ]
    rings: List[List[List[float]]] = []
    for poly in geoms:
        if poly.area <= 0:
            continue
        coords = list(poly.exterior.coords)
        ring = [[round(lat, 8), round(lon, 8)] for lon, lat in coords[:-1]]
        if len(ring) >= 3:
            rings.append(ring)
    return rings


def build_slope_restriction_polygons(
    polygons: Sequence[Sequence[Tuple[float, float]]],
    *,
    slope_limit_pct: float = 6.0,
    grid_m: float = 20.0,
    max_area_ha: float = 10_000.0,
) -> Dict[str, Any]:
    """Return lat/lon no-build rings for cells whose slope exceeds threshold."""
    enabled = [list(poly) for poly in polygons if poly and len(poly) >= 3]
    if not enabled:
        return {"restriction_polygons": [], "excluded_area_ha": 0.0, "cell_count": 0}
    if boundaries_union_area_ha(enabled) > max_area_ha:
        raise ValueError("Site is too large for automatic slope exclusions")

    analysis = run_topo_analysis(
        polygons=enabled,
        grid_m=grid_m,
        allow_coarsen=True,
        contour_minor=1.0,
        contour_major=5.0,
    )
    X = analysis["X"]
    Y = analysis["Y"]
    slope = analysis["slope_grid"]
    mask = np.isfinite(slope) & (slope > float(slope_limit_pct))
    rows, cols = slope.shape
    cells = []
    for r in range(rows):
        for c in range(cols):
            if not bool(mask[r, c]):
                continue
            lon = float(X[r, c])
            lat = float(Y[r, c])
            if math.isnan(lon) or math.isnan(lat):
                continue
            hx, hy = _cell_half_steps(X, Y, r, c)
            cells.append(box(lon - hx, lat - hy, lon + hx, lat + hy))

    if not cells:
        return {
            "restriction_polygons": [],
            "excluded_area_ha": 0.0,
            "cell_count": 0,
            "slope_limit_pct": slope_limit_pct,
            "terrain_source_used": analysis.get("terrain_source_used"),
            "grid_m_used": analysis.get("grid_m_used"),
        }

    restricted = unary_union(cells)
    site = _site_union(enabled)
    if site is not None:
        restricted = restricted.intersection(site)
    # Simplify in degree space very lightly to avoid thousands of tiny vertices.
    restricted = restricted.buffer(0).simplify(0.00001, preserve_topology=True)
    rings = _rings_from_geom(restricted)
    return {
        "restriction_polygons": rings,
        "excluded_area_ha": round(boundaries_union_area_ha([
            [(lon, lat) for lat, lon in ring] for ring in rings
        ]), 3) if rings else 0.0,
        "cell_count": int(mask.sum()),
        "slope_limit_pct": slope_limit_pct,
        "terrain_source_used": analysis.get("terrain_source_used"),
        "grid_m_used": analysis.get("grid_m_used"),
    }
