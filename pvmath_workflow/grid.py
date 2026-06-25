"""Grid proximity helpers — nearest substation via OpenStreetMap Overpass."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import requests

USER_AGENT = "PVMath/1.0 (pvmath.com; contact@pvmath.com)"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DEFAULT_RADIUS_KM = 30.0
MAX_RADIUS_KM = 80.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _element_coord(element: dict) -> Optional[Tuple[float, float]]:
    if element.get("type") == "node":
        if "lat" in element and "lon" in element:
            return float(element["lat"]), float(element["lon"])
        return None
    center = element.get("center") or {}
    if center.get("lat") is not None and center.get("lon") is not None:
        return float(center["lat"]), float(center["lon"])
    return None


def _parse_voltage(tags: dict) -> Optional[str]:
    raw = tags.get("voltage") or tags.get("substation:voltage")
    if not raw:
        return None
    return str(raw).replace(";", " / ")


def _grid_rating_km(distance_km: Optional[float]) -> Tuple[str, str]:
    if distance_km is None:
        return "Unknown", "No mapped substation found in search radius"
    if distance_km <= 2:
        return "Excellent", f"{distance_km:.1f} km — very close grid access (verify with DSO)"
    if distance_km <= 5:
        return "Good", f"{distance_km:.1f} km — favourable grid proximity"
    if distance_km <= 10:
        return "Moderate", f"{distance_km:.1f} km — grid connection likely feasible"
    if distance_km <= 20:
        return "Challenging", f"{distance_km:.1f} km — longer interconnection expected"
    return "Remote", f"{distance_km:.1f} km — distant from mapped substations"


def query_substations_overpass(
    lat: float,
    lon: float,
    radius_km: float = DEFAULT_RADIUS_KM,
    timeout_sec: int = 25,
) -> List[dict]:
    """Return raw Overpass elements for power=substation within radius."""
    radius_m = int(min(max(radius_km, 1.0), MAX_RADIUS_KM) * 1000)
    query = f"""
    [out:json][timeout:{timeout_sec}];
    (
      nwr["power"="substation"](around:{radius_m},{lat},{lon});
    );
    out center;
    """
    resp = requests.post(
        OVERPASS_URL,
        data={"data": query},
        headers={"User-Agent": USER_AGENT},
        timeout=timeout_sec + 5,
    )
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("elements") or []


def nearest_substation(
    lat: float,
    lon: float,
    *,
    radius_km: float = DEFAULT_RADIUS_KM,
) -> Dict[str, Any]:
    """
    Find nearest OSM-mapped substation to a site pin.

    Straight-line distance only — indicative, not cable route length.
    """
    try:
        elements = query_substations_overpass(lat, lon, radius_km=radius_km)
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "source": "OpenStreetMap Overpass",
            "search_radius_km": radius_km,
            "disclaimer": (
                "Indicative grid proximity from OpenStreetMap — substation coverage and "
                "voltage tags are incomplete. Verify interconnection with the local DSO/TSO."
            ),
        }

    best: Optional[Dict[str, Any]] = None
    best_dist = float("inf")

    for el in elements:
        coord = _element_coord(el)
        if not coord:
            continue
        slat, slon = coord
        dist = _haversine_km(lat, lon, slat, slon)
        if dist >= best_dist:
            continue
        tags = el.get("tags") or {}
        best_dist = dist
        best = {
            "osm_type": el.get("type"),
            "osm_id": el.get("id"),
            "name": tags.get("name") or tags.get("operator") or "Unnamed substation",
            "operator": tags.get("operator"),
            "voltage": _parse_voltage(tags),
            "substation_type": tags.get("substation"),
            "lat": round(slat, 6),
            "lon": round(slon, 6),
            "distance_km": round(dist, 2),
        }

    if best is None:
        # Widen once if nothing in default radius
        if radius_km < MAX_RADIUS_KM:
            return nearest_substation(lat, lon, radius_km=MAX_RADIUS_KM)
        rating, detail = _grid_rating_km(None)
        return {
            "success": True,
            "found": False,
            "distance_km": None,
            "rating": rating,
            "detail": detail,
            "search_radius_km": radius_km,
            "source": "OpenStreetMap Overpass",
            "disclaimer": (
                "No substation mapped in OSM within search radius. This does not mean "
                "no grid exists — OSM coverage gaps are common. Confirm with DSO/TSO."
            ),
        }

    rating, detail = _grid_rating_km(best["distance_km"])
    return {
        "success": True,
        "found": True,
        "distance_km": best["distance_km"],
        "rating": rating,
        "detail": detail,
        "nearest": best,
        "search_radius_km": radius_km,
        "source": "OpenStreetMap Overpass",
        "disclaimer": (
            "Straight-line distance to nearest mapped substation — not cable route length. "
            "Voltage and ownership tags from OSM are often incomplete. Verify with DSO/TSO."
        ),
    }
