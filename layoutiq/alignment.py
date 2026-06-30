"""Alignment guide → single layout azimuth (constant across the PV area)."""

from __future__ import annotations

import math
from typing import Optional, Sequence, Tuple

LatLon = Tuple[float, float]  # (lat, lon)


def segment_bearing_deg(a: LatLon, b: LatLon) -> float:
    """Geographic bearing from ``a`` to ``b`` (0° = north, clockwise)."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    d_lon = lon2 - lon1
    y = math.sin(d_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360.0) % 360.0


def _haversine_m(a: LatLon, b: LatLon) -> float:
    r = 6_371_000.0
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def bearing_to_layout_azimuth(bearing: float) -> float:
    """Map geographic bearing to layout azimuth in [90, 270] (undirected axis)."""
    b = bearing % 360.0
    if b > 180.0:
        b -= 180.0
    if b < 90.0:
        b = 180.0 - b
    return max(90.0, min(270.0, b))


def azimuth_from_alignment_polyline(points: Sequence[LatLon]) -> Optional[float]:
    """
    Derive one constant layout azimuth from a multi-point alignment guide.

    Uses length-weighted average of segment bearings so jagged polylines follow
    the engineer's dominant edge direction without varying azimuth per row.
    """
    if len(points) < 2:
        return None
    sum_x = 0.0
    sum_y = 0.0
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        length = _haversine_m(a, b)
        if length < 1e-3:
            continue
        bearing = math.radians(segment_bearing_deg(a, b))
        sum_x += length * math.sin(bearing)
        sum_y += length * math.cos(bearing)
    if sum_x == 0.0 and sum_y == 0.0:
        return None
    avg_bearing = math.degrees(math.atan2(sum_x, sum_y)) % 360.0
    return round(bearing_to_layout_azimuth(avg_bearing), 2)


def layout_rotation_angle(azimuth: float, *, is_tracker: bool) -> float:
    """Rotation applied to the site polygon before row packing (degrees CCW)."""
    if is_tracker:
        return float(azimuth) - 90.0
    return -(float(azimuth) - 180.0)


def resolve_layout_azimuth(
    azimuth: float,
    alignment_polyline: Optional[Sequence[LatLon]] = None,
) -> float:
    """Use alignment guide when present; otherwise the explicit azimuth."""
    if alignment_polyline and len(alignment_polyline) >= 2:
        derived = azimuth_from_alignment_polyline(alignment_polyline)
        if derived is not None:
            return derived
    return float(azimuth)
