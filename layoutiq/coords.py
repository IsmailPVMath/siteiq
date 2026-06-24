"""Local metre projection helpers for layout geometry."""

from __future__ import annotations

import math

_R = 6_371_000.0


def latlon_to_xy(latlons, ref_lat: float, ref_lon: float):
    cos_ref = math.cos(math.radians(ref_lat))
    return [
        (
            (lon - ref_lon) * math.pi / 180 * _R * cos_ref,
            (lat - ref_lat) * math.pi / 180 * _R,
        )
        for lat, lon in latlons
    ]


def xy_to_latlon(xys, ref_lat: float, ref_lon: float):
    cos_ref = math.cos(math.radians(ref_lat))
    return [
        (
            ref_lat + y * 180 / (math.pi * _R),
            ref_lon + x * 180 / (math.pi * _R * cos_ref),
        )
        for x, y in xys
    ]
