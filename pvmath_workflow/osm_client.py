"""Shared OpenStreetMap Overpass client for PVMath GIS workflows."""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence, Tuple

import requests

USER_AGENT = "PVMath/1.0 (pvmath.com; contact@pvmath.com)"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DEFAULT_TIMEOUT_SEC = 90


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bbox_from_rings(
    rings: Sequence[Sequence[Tuple[float, float]]],
    *,
    pad_deg: float = 0.003,
) -> Tuple[float, float, float, float]:
    """Return (south, west, north, east) for Overpass bbox queries. Rings are (lat, lon)."""
    lats: list[float] = []
    lons: list[float] = []
    for ring in rings:
        for lat, lon in ring:
            lats.append(float(lat))
            lons.append(float(lon))
    if not lats:
        raise ValueError("No coordinates in rings")
    south = min(lats) - pad_deg
    north = max(lats) + pad_deg
    west = min(lons) - pad_deg
    east = max(lons) + pad_deg
    return south, west, north, east


def ring_to_overpass_poly(ring: Sequence[Tuple[float, float]]) -> str:
    """Format a closed ring as Overpass poly string (lat lon pairs)."""
    pts = [(float(lat), float(lon)) for lat, lon in ring]
    if len(pts) < 3:
        raise ValueError("Ring needs at least 3 points")
    if pts[0] != pts[-1]:
        pts = [*pts, pts[0]]
    return " ".join(f"{lat} {lon}" for lat, lon in pts)


def overpass_query(
    query: str,
    *,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> list[dict[str, Any]]:
    resp = requests.post(
        OVERPASS_URL,
        data={"data": query},
        headers={"User-Agent": USER_AGENT},
        timeout=timeout_sec + 10,
    )
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("elements") or []


def build_site_constraint_query(
    rings: Sequence[Sequence[Tuple[float, float]]],
    *,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    use_poly: bool = True,
) -> str:
    """Single Overpass request for roads, rail, buildings, water, forest, power lines."""
    if use_poly and rings:
        poly = ring_to_overpass_poly(rings[0])
        area_filter = f'poly:"{poly}"'
    else:
        south, west, north, east = bbox_from_rings(rings)
        area_filter = f"{south},{west},{north},{east}"

    return f"""
[out:json][timeout:{timeout_sec}];
(
  way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|service|track)$"]({area_filter});
  way["railway"]({area_filter});
  way["building"]({area_filter});
  way["natural"="water"]({area_filter});
  way["waterway"~"^(river|stream|canal|ditch)$"]({area_filter});
  way["landuse"="forest"]({area_filter});
  way["natural"="wood"]({area_filter});
  way["power"="line"]({area_filter});
  way["power"="minor_line"]({area_filter});
  relation["power"="line"]({area_filter});
);
out geom;
"""
