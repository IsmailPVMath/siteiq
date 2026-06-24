"""Row-sweep layout algorithm (flat site — DEM integration planned)."""

from __future__ import annotations

import math

from shapely.affinity import rotate as shp_rotate
from shapely.geometry import LineString, MultiLineString, Polygon, box

from layoutiq.coords import latlon_to_xy


def run_layout(
    latlons,
    module_h: float,
    module_w: float,
    n_portrait: int,
    pitch: float,
    setback: float,
    azimuth: float,
    mounting_type: str = "fixed_tilt",
    inter_gap: float = 0.01,
):
    """
    Sweep horizontal bands across a rotated boundary polygon.

    fixed_tilt: rows E-W, pitch N-S, azimuth applies.
    sat: rows N-S, pitch E-W, azimuth ignored.
    """
    is_tracker = mounting_type == "sat"

    lats = [p[0] for p in latlons]
    lons = [p[1] for p in latlons]
    ref_lat = sum(lats) / len(lats)
    ref_lon = sum(lons) / len(lons)

    xy = latlon_to_xy(latlons, ref_lat, ref_lon)
    poly_m = Polygon(xy)
    if not poly_m.is_valid:
        poly_m = poly_m.buffer(0)

    area_m2 = poly_m.area
    poly_inset = poly_m.buffer(-setback)
    if poly_inset.is_empty or poly_inset.area < 4:
        return None

    if is_tracker:
        rot_angle = 90.0
        row_ns = module_w * n_portrait
        mod_ew = module_h + inter_gap
    else:
        rot_angle = -(azimuth - 180.0)
        row_ns = module_h * n_portrait
        mod_ew = module_w + inter_gap

    ctr = poly_inset.centroid
    poly_rot = shp_rotate(poly_inset, rot_angle, origin=(ctr.x, ctr.y))
    minx, miny, maxx, maxy = poly_rot.bounds

    rows_data = []
    rows_polys = []
    y = miny
    while y + row_ns <= maxy:
        band = box(minx - 1, y, maxx + 1, y + row_ns)
        fp = poly_rot.intersection(band)

        if not fp.is_empty:
            cy = y + row_ns / 2
            sweep = LineString([(minx - 1, cy), (maxx + 1, cy)])
            isect = poly_rot.intersection(sweep)

            segs = []
            if isect.geom_type == "LineString":
                segs = [isect]
            elif isect.geom_type == "MultiLineString":
                segs = list(isect.geoms)
            elif isect.geom_type == "GeometryCollection":
                segs = [g for g in isect.geoms if g.geom_type == "LineString"]

            for seg in segs:
                n_mod = int(seg.length / mod_ew)
                if n_mod < 1:
                    continue
                actual_len = n_mod * mod_ew
                x0 = seg.bounds[0]
                row_rect = box(x0, y, x0 + actual_len, y + row_ns)
                row_orig = shp_rotate(row_rect, -rot_angle, origin=(ctr.x, ctr.y))
                rows_polys.append(row_orig)
                rows_data.append(
                    {
                        "n_modules": n_mod,
                        "length_m": round(actual_len, 2),
                        "y_rot_m": round(y, 1),
                    }
                )
        y += pitch

    if not rows_data:
        return None

    total_modules = sum(r["n_modules"] for r in rows_data)
    return {
        "rows_data": rows_data,
        "rows_polys": rows_polys,
        "poly_m": poly_m,
        "poly_inset": poly_inset,
        "total_modules": total_modules,
        "total_rows": len(rows_data),
        "area_m2": area_m2,
        "area_ha": round(area_m2 / 10_000, 3),
        "ref_lat": ref_lat,
        "ref_lon": ref_lon,
        "row_ns": row_ns,
        "n_portrait": n_portrait,
        "is_tracker": is_tracker,
        "mounting_type": mounting_type,
    }
