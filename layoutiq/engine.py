"""Row-sweep layout algorithm with string packing and N-S access blocks."""

from __future__ import annotations

import math
from typing import Any

from shapely.affinity import rotate as shp_rotate
from shapely.geometry import LineString, MultiLineString, Polygon, box
from shapely.ops import unary_union

from layoutiq.coords import latlon_to_xy


def count_strings_in_length(
    length_m: float,
    *,
    modules_per_string: int,
    module_w: float,
    inter_string_gap_m: float,
) -> int:
    """
    Whole strings only along the row (torque tube / row axis).
    Partial strings at the end are dropped.
    """
    if length_m <= 0 or modules_per_string < 1:
        return 0
    string_len = modules_per_string * module_w
    if string_len <= 0:
        return 0
    gap = max(0.0, inter_string_gap_m)
    unit = string_len + gap
    if unit <= 0:
        return 0
    if length_m < string_len:
        return 0
    return int((length_m + gap) // unit)


def string_packed_length(
    n_strings: int,
    *,
    modules_per_string: int,
    module_w: float,
    inter_string_gap_m: float,
) -> float:
    if n_strings <= 0:
        return 0.0
    string_len = modules_per_string * module_w
    gap = max(0.0, inter_string_gap_m)
    return n_strings * string_len + max(0, n_strings - 1) * gap


def pack_tracker_units(
    length_m: float,
    *,
    tracker_string_options: list[int],
    max_tracker_length_m: float,
    modules_per_string: int,
    module_w: float,
    inter_string_gap_m: float,
) -> tuple[list[int], float]:
    """
    Greedily pack whole tracker units (8S/7S/6S/5S...) along a row segment.

    Each unit is made from whole strings; each string has ``modules_per_string``
    modules. Options whose physical unit length exceeds max_tracker_length_m are
    ignored. Partial tracker units are not placed.
    """
    options = sorted({int(v) for v in tracker_string_options if int(v) > 0}, reverse=True)
    if not options:
        options = [8, 7, 6, 5]
    gap = max(0.0, inter_string_gap_m)
    remaining = max(0.0, length_m)
    units: list[int] = []
    used = 0.0

    def unit_len(strings: int) -> float:
        return string_packed_length(
            strings,
            modules_per_string=modules_per_string,
            module_w=module_w,
            inter_string_gap_m=inter_string_gap_m,
        )

    feasible = [
        s
        for s in options
        if unit_len(s) <= max_tracker_length_m + 1e-9 and unit_len(s) <= length_m + 1e-9
    ]
    if not feasible:
        return [], 0.0

    while remaining > 0:
        chosen = None
        chosen_len = 0.0
        for strings in feasible:
            candidate_len = unit_len(strings)
            extra_gap = gap if units else 0.0
            if candidate_len + extra_gap <= remaining + 1e-9:
                chosen = strings
                chosen_len = candidate_len + extra_gap
                break
        if chosen is None:
            break
        units.append(chosen)
        used += chosen_len
        remaining -= chosen_len
    return units, used


def _line_length(geom) -> float:
    if geom.is_empty:
        return 0.0
    if geom.geom_type == "LineString":
        return geom.length
    if geom.geom_type == "MultiLineString":
        return sum(g.length for g in geom.geoms)
    if geom.geom_type == "GeometryCollection":
        return sum(_line_length(g) for g in geom.geoms)
    return 0.0


def _snap_y_origin(miny: float, pitch: float) -> float:
    if pitch <= 0:
        return miny
    return math.floor(miny / pitch) * pitch


def _available_row_length(
    poly_rot: Polygon,
    *,
    south_fence_x: float | None,
    west_fence_x: float | None,
    cy: float,
    is_tracker: bool,
    search_m: float = 2500.0,
) -> float:
    """Measure buildable row-axis length from the field fence inward."""
    if is_tracker:
        x0 = south_fence_x if south_fence_x is not None else poly_rot.bounds[2]
        sweep = LineString([(x0 - search_m, cy), (x0, cy)])
    else:
        x0 = west_fence_x if west_fence_x is not None else poly_rot.bounds[0]
        sweep = LineString([(x0, cy), (x0 + search_m, cy)])
    return _line_length(poly_rot.intersection(sweep))


def _string_rects_rotated(
    *,
    south_fence_x: float | None,
    west_fence_x: float | None,
    y: float,
    row_ns: float,
    n_strings: int,
    modules_per_string: int,
    module_w: float,
    inter_string_gap_m: float,
    is_tracker: bool,
) -> list[Polygon]:
    """Solid string blocks in rotated coordinates (gaps not drawn)."""
    if n_strings < 1:
        return []
    string_len = modules_per_string * module_w
    gap = max(0.0, inter_string_gap_m)
    rects: list[Polygon] = []
    if is_tracker:
        x_cursor = south_fence_x if south_fence_x is not None else 0.0
        for _ in range(n_strings):
            x1 = x_cursor
            x0 = x1 - string_len
            rects.append(box(x0, y, x1, y + row_ns))
            x_cursor = x0 - gap
    else:
        x_cursor = west_fence_x if west_fence_x is not None else 0.0
        for _ in range(n_strings):
            x0 = x_cursor
            x1 = x0 + string_len
            rects.append(box(x0, y, x1, y + row_ns))
            x_cursor = x1 + gap
    return rects


def _prepare_poly_inset(
    latlons,
    setback: float,
    restriction_latlons,
    ref_lat: float,
    ref_lon: float,
):
    xy = latlon_to_xy(latlons, ref_lat, ref_lon)
    poly_m = Polygon(xy)
    if not poly_m.is_valid:
        poly_m = poly_m.buffer(0)
    area_m2 = poly_m.area
    poly_inset = poly_m.buffer(-setback)
    if poly_inset.is_empty or poly_inset.area < 4:
        return None

    restriction_polys = []
    for ring in restriction_latlons or []:
        if not ring or len(ring) < 3:
            continue
        rxy = latlon_to_xy(ring, ref_lat, ref_lon)
        rpoly = Polygon(rxy)
        if not rpoly.is_valid:
            rpoly = rpoly.buffer(0)
        if not rpoly.is_empty:
            restriction_polys.append(rpoly)
    if restriction_polys:
        restricted = unary_union(restriction_polys)
        poly_inset = poly_inset.difference(restricted)
        if poly_inset.is_empty or getattr(poly_inset, "area", 0) < 4:
            return None

    return {
        "poly_m": poly_m,
        "poly_inset": poly_inset,
        "area_m2": area_m2,
    }


def run_layout(
    latlons,
    module_h: float,
    module_w: float,
    n_portrait: int,
    pitch: float,
    setback: float,
    azimuth: float,
    mounting_type: str = "fixed_tilt",
    modules_per_string: int = 28,
    inter_string_gap_m: float = 0.5,
    tracker_string_options: list[int] | None = None,
    max_tracker_length_m: float = 260.0,
    rows_per_block: int = 0,
    block_gap_m: float = 0.0,
    restriction_latlons=None,
    ref_lat: float = None,
    ref_lon: float = None,
    *,
    grid_y_origin: float | None = None,
    south_fence_x: float | None = None,
    west_fence_x: float | None = None,
    rotate_origin: tuple[float, float] | None = None,
):
    """
    Sweep row bands across a rotated boundary polygon on a shared site grid.

    fixed_tilt: rows E-W, pitch N-S, azimuth applies.
    sat: rows N-S, pitch E-W, azimuth ignored.

    When ``grid_y_origin``, ``south_fence_x`` / ``west_fence_x``, and
    ``rotate_origin`` are supplied (multi-parcel coordinated layout), every
    parcel shares the same row pitch lines and south/west fence alignment.
    """
    is_tracker = mounting_type == "sat"
    use_blocks = rows_per_block > 0 and block_gap_m > 0

    lats = [p[0] for p in latlons]
    lons = [p[1] for p in latlons]
    if ref_lat is None:
        ref_lat = sum(lats) / len(lats)
    if ref_lon is None:
        ref_lon = sum(lons) / len(lons)

    prepared = _prepare_poly_inset(latlons, setback, restriction_latlons, ref_lat, ref_lon)
    if not prepared:
        return None
    poly_m = prepared["poly_m"]
    poly_inset = prepared["poly_inset"]
    area_m2 = prepared["area_m2"]

    if is_tracker:
        rot_angle = 90.0
        row_ns = module_h * n_portrait
    else:
        rot_angle = -(azimuth - 180.0)
        row_ns = module_h * n_portrait

    origin = rotate_origin if rotate_origin is not None else (poly_inset.centroid.x, poly_inset.centroid.y)
    poly_rot = shp_rotate(poly_inset, rot_angle, origin=origin)
    minx, miny, maxx, maxy = poly_rot.bounds

    parcel_south = south_fence_x if south_fence_x is not None else maxx
    parcel_west = west_fence_x if west_fence_x is not None else minx

    y = grid_y_origin if grid_y_origin is not None else _snap_y_origin(miny, pitch)
    rows_data: list[dict[str, Any]] = []
    rows_polys: list[Polygon] = []
    string_polys: list[Polygon] = []
    rows_in_block = 0

    while y + row_ns <= maxy + 1e-6:
        cy = y + row_ns / 2
        avail_len = _available_row_length(
            poly_rot,
            south_fence_x=parcel_south,
            west_fence_x=parcel_west,
            cy=cy,
            is_tracker=is_tracker,
        )
        if avail_len < module_w * modules_per_string * 0.5:
            y += pitch
            rows_in_block += 1
            if use_blocks and rows_in_block >= rows_per_block:
                y += block_gap_m
                rows_in_block = 0
            continue

        tracker_units: list[int] = []
        if is_tracker:
            tracker_units, actual_len = pack_tracker_units(
                avail_len,
                tracker_string_options=tracker_string_options or [8, 7, 6, 5],
                max_tracker_length_m=max_tracker_length_m,
                modules_per_string=modules_per_string,
                module_w=module_w,
                inter_string_gap_m=inter_string_gap_m,
            )
            n_strings = sum(tracker_units)
        else:
            n_strings = count_strings_in_length(
                avail_len,
                modules_per_string=modules_per_string,
                module_w=module_w,
                inter_string_gap_m=inter_string_gap_m,
            )
            actual_len = string_packed_length(
                n_strings,
                modules_per_string=modules_per_string,
                module_w=module_w,
                inter_string_gap_m=inter_string_gap_m,
            )

        if n_strings >= 1:
            if is_tracker:
                row_rect = box(parcel_south - actual_len, y, parcel_south, y + row_ns)
            else:
                row_rect = box(parcel_west, y, parcel_west + actual_len, y + row_ns)
            row_clipped = row_rect.intersection(poly_rot)
            if not row_clipped.is_empty and row_clipped.area > row_ns * module_w * 0.5:
                row_orig = shp_rotate(row_clipped, -rot_angle, origin=origin)
                if row_orig.geom_type == "Polygon":
                    rows_polys.append(row_orig)
                elif row_orig.geom_type == "MultiPolygon":
                    rows_polys.extend(row_orig.geoms)

                for srect in _string_rects_rotated(
                    south_fence_x=parcel_south,
                    west_fence_x=parcel_west,
                    y=y,
                    row_ns=row_ns,
                    n_strings=n_strings,
                    modules_per_string=modules_per_string,
                    module_w=module_w,
                    inter_string_gap_m=inter_string_gap_m,
                    is_tracker=is_tracker,
                ):
                    s_clipped = srect.intersection(poly_rot)
                    if s_clipped.is_empty:
                        continue
                    s_orig = shp_rotate(s_clipped, -rot_angle, origin=origin)
                    if s_orig.geom_type == "Polygon":
                        string_polys.append(s_orig)
                    elif s_orig.geom_type == "MultiPolygon":
                        string_polys.extend(g for g in s_orig.geoms if not g.is_empty)

                n_mod = n_strings * modules_per_string
                rows_data.append(
                    {
                        "n_modules": n_mod,
                        "n_strings": n_strings,
                        "tracker_units": tracker_units,
                        "length_m": round(actual_len, 2),
                        "y_rot_m": round(y, 1),
                    }
                )

        y += pitch
        rows_in_block += 1
        if use_blocks and rows_in_block >= rows_per_block:
            y += block_gap_m
            rows_in_block = 0

    if not rows_data:
        return None

    total_modules = sum(r["n_modules"] for r in rows_data)
    total_strings = sum(r["n_strings"] for r in rows_data)
    total_tracker_units = sum(len(r.get("tracker_units") or []) for r in rows_data)
    return {
        "rows_data": rows_data,
        "rows_polys": rows_polys,
        "string_polys": string_polys,
        "poly_m": poly_m,
        "poly_inset": poly_inset,
        "total_modules": total_modules,
        "total_strings": total_strings,
        "total_tracker_units": total_tracker_units,
        "total_rows": len(rows_data),
        "area_m2": area_m2,
        "area_ha": round(area_m2 / 10_000, 3),
        "ref_lat": ref_lat,
        "ref_lon": ref_lon,
        "row_ns": row_ns,
        "n_portrait": n_portrait,
        "is_tracker": is_tracker,
        "mounting_type": mounting_type,
        "modules_per_string": modules_per_string,
        "inter_string_gap_m": inter_string_gap_m,
        "tracker_string_options": tracker_string_options or [8, 7, 6, 5],
        "max_tracker_length_m": max_tracker_length_m,
        "rows_per_block": rows_per_block,
        "block_gap_m": block_gap_m,
    }


def site_layout_grid(
    polys_latlon: list[list[tuple[float, float]]],
    *,
    setback: float,
    restriction_latlons,
    ref_lat: float,
    ref_lon: float,
    pitch: float,
    azimuth: float,
    is_tracker: bool,
) -> dict[str, Any] | None:
    """Compute shared rotation origin and fence lines for coordinated multi-parcel layout."""
    insets = []
    for poly in polys_latlon:
        prepared = _prepare_poly_inset(poly, setback, restriction_latlons, ref_lat, ref_lon)
        if prepared:
            insets.append(prepared["poly_inset"])
    if not insets:
        return None

    union = unary_union(insets)
    if union.is_empty:
        return None
    origin_pt = union.centroid
    origin = (origin_pt.x, origin_pt.y)
    rot_angle = 90.0 if is_tracker else -(azimuth - 180.0)
    rotated = shp_rotate(union, rot_angle, origin=origin)
    minx, miny, maxx, maxy = rotated.bounds
    return {
        "rotate_origin": origin,
        "grid_y_origin": _snap_y_origin(miny, pitch),
        "south_fence_x": maxx,
        "west_fence_x": minx,
        "rot_angle": rot_angle,
        "y_max": maxy,
    }
