"""TerrainIQ terrain mesh for browser-side 3D visualization."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

from pvmath_topo_engine import boundaries_union_area_ha, compute_slope, run_topo_analysis


def _local_xy(lon: float, lat: float, lon_c: float, lat_c: float) -> Tuple[float, float]:
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat_c))
    return (lon - lon_c) * m_per_deg_lon, (lat - lat_c) * m_per_deg_lat


def _stride_for_shape(shape: Tuple[int, int], max_vertices: int) -> int:
    rows, cols = shape
    if rows * cols <= max_vertices:
        return 1
    return max(1, int(math.ceil(math.sqrt((rows * cols) / max_vertices))))


def _mesh_from_tile(
    tile: Dict[str, Any],
    *,
    lon_c: float,
    lat_c: float,
    z0: float,
    max_vertices: int,
) -> Tuple[List[List[float]], List[float], List[float], List[List[int]]]:
    X = tile["X"]
    Y = tile["Y"]
    Z = tile["Z"]
    slope = tile.get("slope_grid")
    grid_m = float(tile.get("grid_m", 5.0))
    if slope is None:
        slope = compute_slope(Z, grid_m)

    stride = _stride_for_shape(Z.shape, max_vertices)
    Xs = X[::stride, ::stride]
    Ys = Y[::stride, ::stride]
    Zs = Z[::stride, ::stride]
    Ss = slope[::stride, ::stride]

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

    return vertices, elevations, slopes, faces


def build_terrain_mesh(
    polygons: Sequence[Sequence[Tuple[float, float]]],
    *,
    grid_m: float = 20.0,
    max_vertices: int = 12_000,
    mask_geojson: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return a compact triangular mesh from TerrainIQ DEM grids."""
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
    bbox = analysis["bbox"]
    lat_c = float(bbox["lat_c"])
    lon_c = float(bbox["lon_c"])

    tiles = analysis.get("tiles") or [
        {
            "X": analysis["X"],
            "Y": analysis["Y"],
            "Z": analysis["Z"],
            "slope_grid": analysis["slope_grid"],
            "grid_m": analysis["grid_m_used"],
        }
    ]

    z_mins: List[float] = []
    for tile in tiles:
        Z = tile["Z"]
        valid = Z[~np.isnan(Z)]
        if len(valid):
            z_mins.append(float(valid.min()))
    if not z_mins:
        raise ValueError("NO_TERRAIN_POINTS")
    z0 = min(z_mins)

    per_tile_budget = max(500, int(max_vertices / max(1, len(tiles))))
    vertices: List[List[float]] = []
    elevations: List[float] = []
    slopes: List[float] = []
    faces: List[List[int]] = []
    for tile in tiles:
        t_verts, t_elevs, t_slopes, t_faces = _mesh_from_tile(
            tile,
            lon_c=lon_c,
            lat_c=lat_c,
            z0=z0,
            max_vertices=per_tile_budget,
        )
        if not t_verts:
            continue
        offset = len(vertices)
        vertices.extend(t_verts)
        elevations.extend(t_elevs)
        slopes.extend(t_slopes)
        faces.extend([[a + offset, b + offset, c + offset] for a, b, c in t_faces])

    if not vertices:
        raise ValueError("NO_TERRAIN_POINTS")

    valid_z = np.array(elevations, dtype=float)
    return {
        "vertices": vertices,
        "faces": faces,
        "elevations": elevations,
        "slopes": slopes,
        "origin": {"lat": lat_c, "lon": lon_c, "elevation_m": z0},
        "bbox": bbox,
        "grid_m_used": float(analysis["grid_m_used"]),
        "terrain_source_used": analysis["terrain_source_used"],
        "z_min": float(valid_z.min()),
        "z_max": float(valid_z.max()),
        "slope_mean": float(analysis["slope"]["mean"]),
        "coverage_gaps": analysis.get("coverage_gaps") or [],
        "multi_cluster": bool(analysis.get("multi_cluster")),
        "cluster_count": int(analysis.get("cluster_count") or 1),
    }
