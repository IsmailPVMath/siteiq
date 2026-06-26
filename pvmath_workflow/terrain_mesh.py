"""TopoIQ terrain mesh for browser-side 3D visualization."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

from pvmath_topo_engine import boundaries_union_area_ha, run_topo_analysis


def _local_xy(lon: float, lat: float, lon_c: float, lat_c: float) -> Tuple[float, float]:
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat_c))
    return (lon - lon_c) * m_per_deg_lon, (lat - lat_c) * m_per_deg_lat


def _stride_for_shape(shape: Tuple[int, int], max_vertices: int) -> int:
    rows, cols = shape
    if rows * cols <= max_vertices:
        return 1
    return max(1, int(math.ceil(math.sqrt((rows * cols) / max_vertices))))


def build_terrain_mesh(
    polygons: Sequence[Sequence[Tuple[float, float]]],
    *,
    grid_m: float = 20.0,
    max_vertices: int = 12_000,
    mask_geojson: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return a compact triangular mesh from TopoIQ DEM grids."""
    enabled_polys = [list(poly) for poly in polygons if poly and len(poly) >= 3]
    if not enabled_polys:
        raise ValueError("NO_BOUNDARY")
    if boundaries_union_area_ha(enabled_polys) > 10_000:
        raise ValueError("Site is too large for browser terrain mesh")

    analysis = run_topo_analysis(
        polygons=enabled_polys,
        grid_m=grid_m,
        allow_coarsen=True,
        contour_minor=1.0,
        contour_major=5.0,
        mask_geojson=mask_geojson,
    )
    X = analysis["X"]
    Y = analysis["Y"]
    Z = analysis["Z"]
    slope = analysis["slope_grid"]
    bbox = analysis["bbox"]
    lat_c = float(bbox["lat_c"])
    lon_c = float(bbox["lon_c"])
    stride = _stride_for_shape(Z.shape, max_vertices)

    Xs = X[::stride, ::stride]
    Ys = Y[::stride, ::stride]
    Zs = Z[::stride, ::stride]
    Ss = slope[::stride, ::stride]
    valid_z = Zs[~np.isnan(Zs)]
    if len(valid_z) == 0:
        raise ValueError("NO_TERRAIN_POINTS")
    z0 = float(valid_z.min())

    vertex_index: Dict[Tuple[int, int], int] = {}
    vertices: List[List[float]] = []
    elevations: List[float] = []
    slopes: List[float] = []
    rows, cols = Zs.shape
    for r in range(rows):
        for c in range(cols):
            z = float(Zs[r, c])
            if math.isnan(z):
                continue
            x, y = _local_xy(float(Xs[r, c]), float(Ys[r, c]), lon_c, lat_c)
            vertex_index[(r, c)] = len(vertices)
            vertices.append([round(x, 2), round(y, 2), round(z - z0, 2)])
            elevations.append(round(z, 2))
            s = float(Ss[r, c])
            slopes.append(round(0.0 if math.isnan(s) else s, 2))

    faces: List[List[int]] = []
    for r in range(rows - 1):
        for c in range(cols - 1):
            a = vertex_index.get((r, c))
            b = vertex_index.get((r, c + 1))
            d = vertex_index.get((r + 1, c))
            e = vertex_index.get((r + 1, c + 1))
            if a is not None and b is not None and d is not None:
                faces.append([a, d, b])
            if b is not None and d is not None and e is not None:
                faces.append([b, d, e])

    return {
        "vertices": vertices,
        "faces": faces,
        "elevations": elevations,
        "slopes": slopes,
        "origin": {"lat": lat_c, "lon": lon_c, "elevation_m": z0},
        "bbox": bbox,
        "grid_m_used": float(analysis["grid_m_used"]) * stride,
        "terrain_source_used": analysis["terrain_source_used"],
        "z_min": float(valid_z.min()),
        "z_max": float(valid_z.max()),
        "slope_mean": float(analysis["slope"]["mean"]),
    }
