"""Row-sweep layout algorithm with string packing and N-S access blocks."""

from __future__ import annotations

import math
from typing import Any

from shapely.affinity import rotate as shp_rotate
from shapely.geometry import Polygon, box
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
    n_whole, _, _ = plan_strings_in_length(
        length_m,
        modules_per_string=modules_per_string,
        module_w=module_w,
        inter_string_gap_m=inter_string_gap_m,
        allow_partial=False,
    )
    return n_whole


def plan_strings_in_length(
    length_m: float,
    *,
    modules_per_string: int,
    module_w: float,
    inter_string_gap_m: float,
    allow_partial: bool = False,
) -> tuple[int, int, float]:
    """
    Plan whole + optional partial string placement along a row segment.

    Returns (n_whole_strings, partial_module_count, used_length_m).
    Partial strings require at least half a full string (e.g. 14 of 28 modules).
    """
    if length_m <= 0 or modules_per_string < 1:
        return 0, 0, 0.0
    string_len = modules_per_string * module_w
    if string_len <= 0:
        return 0, 0, 0.0
    gap = max(0.0, inter_string_gap_m)
    unit = string_len + gap
    min_partial_modules = max(1, modules_per_string // 2)

    n_whole = 0
    if length_m >= string_len and unit > 0:
        n_whole = int((length_m + gap) // unit)

    used = string_packed_length(
        n_whole,
        modules_per_string=modules_per_string,
        module_w=module_w,
        inter_string_gap_m=inter_string_gap_m,
    )
    remaining = length_m - used
    partial_modules = 0

    if allow_partial and remaining >= module_w * min_partial_modules:
        gap_before = gap if n_whole > 0 else 0.0
        if remaining >= gap_before + module_w * min_partial_modules:
            fit_modules = int((remaining - gap_before) // module_w)
            if fit_modules >= min_partial_modules:
                partial_modules = min(modules_per_string - 1, fit_modules)
                used += gap_before + partial_modules * module_w

    return n_whole, partial_modules, used


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
    allow_partial: bool = False,
) -> tuple[list[int], int, float]:
    """
    Greedily pack whole tracker units (8S/7S/6S/5S...) along a row segment.

    Each unit is made from whole strings; each string has ``modules_per_string``
    modules. Options whose physical unit length exceeds max_tracker_length_m are
    ignored. When ``allow_partial`` is True, a trailing half-string (or longer)
    may be placed if space remains.
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
        return [], 0, 0.0

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

    partial_modules = 0
    min_partial_modules = max(1, modules_per_string // 2)
    gap_before = gap if units else 0.0
    if allow_partial and remaining >= gap_before + module_w * min_partial_modules:
        fit_modules = int((remaining - gap_before) // module_w)
        if fit_modules >= min_partial_modules:
            partial_modules = min(modules_per_string - 1, fit_modules)
            used += gap_before + partial_modules * module_w

    return units, partial_modules, used


def _snap_y_origin(miny: float, pitch: float) -> float:
    if pitch <= 0:
        return miny
    return math.floor(miny / pitch) * pitch


def _row_band_segments(poly_rot: Polygon, y: float, row_ns: float) -> list[tuple[float, float]]:
    """X-intervals where the row band intersects the buildable polygon (handles concave sites)."""
    minx, _, maxx, _ = poly_rot.bounds
    band = box(minx, y - 1e-6, maxx, y + row_ns + 1e-6)
    clipped = poly_rot.intersection(band)
    if clipped.is_empty:
        return []
    pieces: list[Polygon] = []
    if clipped.geom_type == "Polygon":
        pieces = [clipped]
    elif clipped.geom_type == "MultiPolygon":
        pieces = [g for g in clipped.geoms if not g.is_empty]
    elif clipped.geom_type == "GeometryCollection":
        pieces = [g for g in clipped.geoms if g.geom_type == "Polygon" and not g.is_empty]
    segments: list[tuple[float, float]] = []
    for piece in pieces:
        x0, _, x1, _ = piece.bounds
        if x1 - x0 > 1e-3:
            segments.append((x0, x1))
    return sorted(segments, key=lambda s: s[0])


def _ew_road_bands(
    anchor: float,
    *,
    unit: float,
    cols_per_block: int,
    ew_gap: float,
    lo: float,
    hi: float,
    is_tracker: bool,
) -> list[tuple[float, float]]:
    """Rotated-x ranges occupied by E-W maintenance roads (corridors that cross
    the tracker length). Anchored at the field fence and spaced every
    ``cols_per_block`` strings, so the roads line up across every row."""
    if cols_per_block < 1 or ew_gap <= 0 or unit <= 0:
        return []
    block_len = cols_per_block * unit
    period = block_len + ew_gap
    bands: list[tuple[float, float]] = []
    i = 0
    while i < 100000:
        if is_tracker:
            right = anchor - block_len - i * period
            left = right - ew_gap
            if left < lo - 1e-6:
                break
            if right > lo and left < hi:
                bands.append((left, right))
        else:
            left = anchor + block_len + i * period
            right = left + ew_gap
            if right > hi + 1e-6:
                break
            if left < hi and right > lo:
                bands.append((left, right))
        i += 1
    return bands


def _split_segments_by_roads(
    segments: list[tuple[float, float]], road_bands: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """Cut each row segment wherever it crosses an E-W road band."""
    if not road_bands:
        return segments
    out: list[tuple[float, float]] = []
    for smin, smax in segments:
        pieces = [(smin, smax)]
        for rl, rr in road_bands:
            nxt: list[tuple[float, float]] = []
            for a, b in pieces:
                if rr <= a or rl >= b:
                    nxt.append((a, b))
                    continue
                if a < rl:
                    nxt.append((a, min(rl, b)))
                if b > rr:
                    nxt.append((max(rr, a), b))
            pieces = nxt
        for a, b in pieces:
            if b - a > 1e-6:
                out.append((a, b))
    return sorted(out, key=lambda s: s[0])


def _string_rects_in_segment(
    *,
    x_seg_min: float,
    x_seg_max: float,
    y: float,
    row_ns: float,
    n_strings: int,
    modules_per_string: int,
    module_w: float,
    inter_string_gap_m: float,
    is_tracker: bool,
    partial_modules: int = 0,
) -> list[Polygon]:
    if n_strings < 1 and partial_modules < 1:
        return []
    string_len = modules_per_string * module_w
    gap = max(0.0, inter_string_gap_m)
    rects: list[Polygon] = []
    if is_tracker:
        x_cursor = x_seg_max
        for _ in range(n_strings):
            x1 = x_cursor
            x0 = x1 - string_len
            if x0 < x_seg_min - 1e-6:
                break
            rects.append(box(x0, y, x1, y + row_ns))
            x_cursor = x0 - gap
        if partial_modules > 0:
            x1 = x_cursor
            x0 = x1 - partial_modules * module_w
            if x0 >= x_seg_min - 1e-6:
                rects.append(box(x0, y, x1, y + row_ns))
    else:
        x_cursor = x_seg_min
        for _ in range(n_strings):
            x0 = x_cursor
            x1 = x0 + string_len
            if x1 > x_seg_max + 1e-6:
                break
            rects.append(box(x0, y, x1, y + row_ns))
            x_cursor = x1 + gap
        if partial_modules > 0:
            x0 = x_cursor + (gap if n_strings > 0 else 0.0)
            x1 = x0 + partial_modules * module_w
            if x1 <= x_seg_max + 1e-6:
                rects.append(box(x0, y, x1, y + row_ns))
    return rects


def _accept_string_geom(
    geom,
    full_rect: Polygon,
    *,
    allow_partial: bool,
    min_partial_modules: int,
    module_w: float,
    row_ns: float,
) -> bool:
    """Drop clipped fragments unless partial strings are allowed."""
    if geom is None or geom.is_empty:
        return False
    full_area = full_rect.area
    if full_area <= 0:
        return False
    if geom.geom_type == "Polygon":
        pieces = [geom]
    elif geom.geom_type == "MultiPolygon":
        pieces = [g for g in geom.geoms if not g.is_empty]
    else:
        return allow_partial
    for piece in pieces:
        frac = piece.area / full_area
        if frac >= 0.98:
            return True
        if allow_partial and piece.area >= module_w * min_partial_modules * row_ns * 0.92:
            return True
    return False


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
    """Solid string blocks anchored at site fence (legacy single-segment path)."""
    if is_tracker:
        x_max = south_fence_x if south_fence_x is not None else 0.0
        x_min = x_max - 5000.0
    else:
        x_min = west_fence_x if west_fence_x is not None else 0.0
        x_max = x_min + 5000.0
    return _string_rects_in_segment(
        x_seg_min=x_min,
        x_seg_max=x_max,
        y=y,
        row_ns=row_ns,
        n_strings=n_strings,
        modules_per_string=modules_per_string,
        module_w=module_w,
        inter_string_gap_m=inter_string_gap_m,
        is_tracker=is_tracker,
    )


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
    ns_gap_1_m: float = 0.0,
    restriction_latlons=None,
    ref_lat: float = None,
    ref_lon: float = None,
    *,
    grid_y_origin: float | None = None,
    south_fence_x: float | None = None,
    west_fence_x: float | None = None,
    rotate_origin: tuple[float, float] | None = None,
    allow_partial_strings: bool = False,
    row_alignment: str = "horizontal",
    cols_per_block: int = 0,
    ew_gap_m: float = 0.0,
):
    """
    Sweep row bands across a rotated boundary polygon on a shared site grid.

    fixed_tilt: rows E-W, pitch N-S, azimuth applies.
    sat: rows N-S, pitch E-W, azimuth ignored.

    When ``grid_y_origin``, ``south_fence_x`` / ``west_fence_x``, and
    ``rotate_origin`` are supplied (multi-parcel coordinated layout), every
    parcel shares the same row pitch lines and south/west fence alignment.

    ``row_alignment``:
    - ``horizontal`` (Aligned) — every row snaps its strings to one shared
      string grid anchored at the south (SAT) or west (fixed) fence, so string
      columns line up across all rows. Orderly, best buildability; trims a little
      capacity at the fence end.
    - ``boundary`` (Non-aligned) — pack strings into every polygon pocket to its
      own edge for maximum capacity, with ragged/staggered ends.

    ``rows_per_block`` counts full east–west pitch bands (constant pitch across the
    PV area) before an N-S road at the north end of the block. ``ns_gap_1_m`` and
    ``block_gap_m`` (second N-S gap) are the maintenance gaps inserted on the
    pitch grid at that boundary. When ``ns_gap_1_m`` is 0, the first gap uses
    ``inter_string_gap_m``. ``cols_per_block`` / ``ew_gap_m`` insert E-W roads
    after that many tracker columns, anchored at the fence so they line up
    across the whole field.
    """
    is_tracker = mounting_type == "sat"
    bands_per_block = rows_per_block
    ns_gap_1 = ns_gap_1_m if ns_gap_1_m > 0 else inter_string_gap_m
    use_ns_blocks = bands_per_block > 0 and (ns_gap_1 > 0 or block_gap_m > 0)

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

    # Shared string grid anchor for aligned placement. Every row snaps its
    # strings to grid lines spaced one string-unit apart from the field fence,
    # so string columns line up across all rows (PVcase "Grid" look).
    string_unit = modules_per_string * module_w + max(0.0, inter_string_gap_m)
    grid_anchor_south = south_fence_x if south_fence_x is not None else maxx
    grid_anchor_west = west_fence_x if west_fence_x is not None else minx

    y = grid_y_origin if grid_y_origin is not None else _snap_y_origin(miny, pitch)
    rows_data: list[dict[str, Any]] = []
    rows_polys: list[Polygon] = []
    string_polys: list[Polygon] = []
    string_row_local_idx: list[int] = []
    rows_in_block = 0

    # E-W maintenance roads: fence-anchored gaps every ``cols_per_block`` strings
    # that cross the tracker length, identical for every row so they line up.
    ew_road_bands = _ew_road_bands(
        grid_anchor_south if is_tracker else grid_anchor_west,
        unit=string_unit,
        cols_per_block=cols_per_block,
        ew_gap=ew_gap_m,
        lo=minx,
        hi=maxx,
        is_tracker=is_tracker,
    )

    while y + row_ns <= maxy + 1e-6:
        band_segments = _row_band_segments(poly_rot, y, row_ns)
        if row_alignment == "boundary":
            # Non-aligned: fill every polygon pocket to its own edge — maximum
            # capacity, ragged/staggered string ends.
            segments = band_segments
        else:
            # Aligned: one run per pitch band, snapped to the shared string grid
            # at the field fence so strings align column-wise across every row
            # (orderly, best buildability). Strings over interior gaps (ponds,
            # cut-outs) are dropped later by clipping.
            if band_segments and string_unit > 0:
                outer_min = min(s[0] for s in band_segments)
                outer_max = max(s[1] for s in band_segments)
                if is_tracker:
                    k = max(0, math.ceil((grid_anchor_south - outer_max) / string_unit - 1e-9))
                    snapped_max = grid_anchor_south - k * string_unit
                    segments = (
                        [(outer_min, snapped_max)] if snapped_max - outer_min > 1e-3 else []
                    )
                else:
                    k = max(0, math.ceil((outer_min - grid_anchor_west) / string_unit - 1e-9))
                    snapped_min = grid_anchor_west + k * string_unit
                    segments = (
                        [(snapped_min, outer_max)] if outer_max - snapped_min > 1e-3 else []
                    )
            else:
                segments = []
        if ew_road_bands:
            segments = _split_segments_by_roads(segments, ew_road_bands)

        rows_before = len(rows_data)
        for seg_min, seg_max in segments:
            avail_len = seg_max - seg_min
            if avail_len < module_w * modules_per_string * 0.5:
                continue

            tracker_units: list[int] = []
            partial_modules = 0
            if is_tracker:
                tracker_units, partial_modules, actual_len = pack_tracker_units(
                    avail_len,
                    tracker_string_options=tracker_string_options or [8, 7, 6, 5],
                    max_tracker_length_m=max_tracker_length_m,
                    modules_per_string=modules_per_string,
                    module_w=module_w,
                    inter_string_gap_m=inter_string_gap_m,
                    allow_partial=allow_partial_strings,
                )
                n_strings = sum(tracker_units) + (1 if partial_modules > 0 else 0)
            else:
                n_strings, partial_modules, actual_len = plan_strings_in_length(
                    avail_len,
                    modules_per_string=modules_per_string,
                    module_w=module_w,
                    inter_string_gap_m=inter_string_gap_m,
                    allow_partial=allow_partial_strings,
                )

            if n_strings < 1 and partial_modules < 1:
                continue

            min_partial_modules = max(1, modules_per_string // 2)
            planned_whole = (
                sum(tracker_units)
                if is_tracker
                else n_strings - (1 if partial_modules > 0 else 0)
            )
            string_rects = list(
                _string_rects_in_segment(
                    x_seg_min=seg_min,
                    x_seg_max=seg_max,
                    y=y,
                    row_ns=row_ns,
                    n_strings=planned_whole,
                    modules_per_string=modules_per_string,
                    module_w=module_w,
                    inter_string_gap_m=inter_string_gap_m,
                    is_tracker=is_tracker,
                    partial_modules=partial_modules,
                )
            )
            whole_rects = string_rects[:planned_whole]
            partial_rects = string_rects[planned_whole:]

            placed_clips: list = []
            placed_partial_modules = 0
            accepted_units: list[int] = []

            if is_tracker:
                # A single-axis tracker is a rigid structure: every string in a
                # planned 6/5/4/3-string unit must fit wholly inside the buildable
                # area, otherwise the entire unit is dropped. This prevents
                # clipping (trees, irregular boundary) from leaving invalid 1–2
                # string tracker stubs that can't physically be installed.
                idx = 0
                for unit_strings in tracker_units:
                    unit_rects = whole_rects[idx : idx + unit_strings]
                    idx += unit_strings
                    if len(unit_rects) < unit_strings:
                        continue
                    unit_clips = [r.intersection(poly_rot) for r in unit_rects]
                    unit_ok = all(
                        _accept_string_geom(
                            clip,
                            rect,
                            allow_partial=False,
                            min_partial_modules=min_partial_modules,
                            module_w=module_w,
                            row_ns=row_ns,
                        )
                        for clip, rect in zip(unit_clips, unit_rects)
                    )
                    if not unit_ok:
                        continue
                    placed_clips.extend(unit_clips)
                    accepted_units.append(unit_strings)
                whole_strings = sum(accepted_units)
            else:
                for srect in whole_rects:
                    s_clipped = srect.intersection(poly_rot)
                    if not _accept_string_geom(
                        s_clipped,
                        srect,
                        allow_partial=allow_partial_strings,
                        min_partial_modules=min_partial_modules,
                        module_w=module_w,
                        row_ns=row_ns,
                    ):
                        continue
                    placed_clips.append(s_clipped)
                whole_strings = len(placed_clips)
                for prect in partial_rects:
                    p_clipped = prect.intersection(poly_rot)
                    if _accept_string_geom(
                        p_clipped,
                        prect,
                        allow_partial=allow_partial_strings,
                        min_partial_modules=min_partial_modules,
                        module_w=module_w,
                        row_ns=row_ns,
                    ):
                        placed_clips.append(p_clipped)
                        placed_partial_modules = partial_modules

            n_mod = whole_strings * modules_per_string + placed_partial_modules
            if n_mod < 1:
                # Nothing survived clipping for this band — don't emit an empty row.
                continue

            if is_tracker:
                row_rect = box(seg_max - actual_len, y, seg_max, y + row_ns)
            else:
                row_rect = box(seg_min, y, seg_min + actual_len, y + row_ns)
            row_clipped = row_rect.intersection(poly_rot)
            row_orig = shp_rotate(row_clipped, -rot_angle, origin=origin)
            # On concave parcels a segment can clip into a MultiPolygon — all strings
            # from this segment share the first row-local index for that band.
            row_local_idx = len(rows_polys)
            if row_orig.geom_type == "Polygon":
                rows_polys.append(row_orig)
            elif row_orig.geom_type == "MultiPolygon":
                rows_polys.extend(row_orig.geoms)

            for s_clipped in placed_clips:
                if s_clipped.is_empty:
                    continue
                s_orig = shp_rotate(s_clipped, -rot_angle, origin=origin)
                if s_orig.geom_type == "Polygon":
                    string_polys.append(s_orig)
                    string_row_local_idx.append(row_local_idx)
                elif s_orig.geom_type == "MultiPolygon":
                    for g in s_orig.geoms:
                        if g.is_empty:
                            continue
                        string_polys.append(g)
                        string_row_local_idx.append(row_local_idx)

            rows_data.append(
                {
                    "n_modules": n_mod,
                    "n_strings": whole_strings + (1 if placed_partial_modules > 0 else 0),
                    "partial_modules": placed_partial_modules,
                    "tracker_units": accepted_units if is_tracker else [],
                    "length_m": round(actual_len, 2),
                    "y_rot_m": round(y, 1),
                }
            )

        # Advance one pitch slot. When N-S roads are enabled the road skips a
        # whole number of pitch slots, so every tracker stays on the uniform
        # pitch grid — centre spacing is always a multiple of pitch (e.g.
        # 7, 7, 14, 7, 7, 14 …), never an off-grid value. Only bands that
        # actually placed trackers count toward a block, so empty bands outside
        # the buildable area never trigger a road.
        y += pitch
        if use_ns_blocks and len(rows_data) > rows_before:
            rows_in_block += 1
            if rows_in_block >= bands_per_block:
                if ns_gap_1 > 0:
                    y += max(1, math.ceil(ns_gap_1 / pitch)) * pitch
                if block_gap_m > 0:
                    y += max(1, math.ceil(block_gap_m / pitch)) * pitch
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
        "string_row_local_idx": string_row_local_idx,
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
        "ns_gap_1_m": ns_gap_1_m,
        "ns_gap_1_effective_m": ns_gap_1,
        "bands_per_block": bands_per_block,
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
