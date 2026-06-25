"""Row-sweep layout algorithm with string packing and N-S access blocks."""

from __future__ import annotations

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
    # First string needs no leading gap; each extra string needs gap + string_len
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
        s for s in options
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
    rows_per_block: int = 2,
    block_gap_m: float = 5.0,
    restriction_latlons=None,
    ref_lat: float = None,
    ref_lon: float = None,
):
    """
    Sweep row bands across a rotated boundary polygon.

    fixed_tilt: rows E-W, pitch N-S, azimuth applies.
    sat: rows N-S, pitch E-W, azimuth ignored.

    Modules are placed in whole strings along each row with ``inter_string_gap_m``
    between strings (default 500 mm). Partial strings are dropped.

    Access roads (N-S only): after every ``rows_per_block`` rows, an extra
    ``block_gap_m`` is inserted before the next row. Set ``rows_per_block`` to 0
    to disable block gaps.

    ref_lat/ref_lon override the local projection origin for multi-parcel layouts.
    """
    is_tracker = mounting_type == "sat"
    use_blocks = rows_per_block > 0 and block_gap_m > 0

    lats = [p[0] for p in latlons]
    lons = [p[1] for p in latlons]
    if ref_lat is None:
        ref_lat = sum(lats) / len(lats)
    if ref_lon is None:
        ref_lon = sum(lons) / len(lons)

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
        if poly_inset.is_empty or poly_inset.area < 4:
            return None

    if is_tracker:
        rot_angle = 90.0
        row_ns = module_h * n_portrait
    else:
        rot_angle = -(azimuth - 180.0)
        row_ns = module_h * n_portrait

    ctr = poly_inset.centroid
    poly_rot = shp_rotate(poly_inset, rot_angle, origin=(ctr.x, ctr.y))
    minx, miny, maxx, maxy = poly_rot.bounds

    rows_data = []
    rows_polys = []
    rows_in_block = 0
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
                tracker_units = []
                if is_tracker:
                    tracker_units, actual_len = pack_tracker_units(
                        seg.length,
                        tracker_string_options=tracker_string_options or [8, 7, 6, 5],
                        max_tracker_length_m=max_tracker_length_m,
                        modules_per_string=modules_per_string,
                        module_w=module_w,
                        inter_string_gap_m=inter_string_gap_m,
                    )
                    n_strings = sum(tracker_units)
                else:
                    n_strings = count_strings_in_length(
                        seg.length,
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
                if n_strings < 1:
                    continue
                n_mod = n_strings * modules_per_string
                x0 = seg.bounds[0]
                row_rect = box(x0, y, x0 + actual_len, y + row_ns)
                row_orig = shp_rotate(row_rect, -rot_angle, origin=(ctr.x, ctr.y))
                rows_polys.append(row_orig)
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
