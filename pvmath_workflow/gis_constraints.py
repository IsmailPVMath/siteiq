"""Detect site constraints from OpenStreetMap and return categorized GeoJSON layers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from shapely.geometry import LineString, Polygon, mapping, shape
from shapely.ops import unary_union

from pvmath_workflow.osm_client import build_site_constraint_query, overpass_query

# Display order and colours for the interactive map (hex).
LAYER_STYLES: Dict[str, Dict[str, str]] = {
    "roads": {"color": "#64748b", "fillColor": "#94a3b8"},
    "railways": {"color": "#475569", "fillColor": "#64748b"},
    "buildings": {"color": "#dc2626", "fillColor": "#fca5a5"},
    "rivers": {"color": "#2563eb", "fillColor": "#93c5fd"},
    "lakes": {"color": "#1d4ed8", "fillColor": "#60a5fa"},
    "canals": {"color": "#0284c7", "fillColor": "#7dd3fc"},
    "forests": {"color": "#15803d", "fillColor": "#86efac"},
    "water_bodies": {"color": "#0369a1", "fillColor": "#38bdf8"},
    "transmission_lines": {"color": "#ea580c", "fillColor": "#fdba74"},
}

DEFAULT_SETBACKS_M: Dict[str, float] = {
    "site_boundary": 5.0,
    "roads": 5.0,
    "railways": 30.0,
    "buildings": 10.0,
    "rivers": 50.0,
    "lakes": 50.0,
    "canals": 30.0,
    "forests": 20.0,
    "water_bodies": 50.0,
    "transmission_lines": 100.0,
}


def _way_geom(element: dict) -> Optional[Any]:
    coords = element.get("geometry") or []
    if len(coords) < 2:
        return None
    pts = [(float(c["lon"]), float(c["lat"])) for c in coords]
    if pts[0] == pts[-1] and len(pts) >= 4:
        geom = Polygon(pts)
    else:
        geom = LineString(pts)
    if not geom.is_valid:
        geom = geom.buffer(0)
    return geom if not geom.is_empty else None


def _categorize(tags: dict) -> Optional[str]:
    if tags.get("highway"):
        return "roads"
    if tags.get("railway"):
        return "railways"
    if tags.get("building"):
        return "buildings"
    ww = tags.get("waterway")
    if ww in ("river", "stream", "ditch"):
        return "rivers"
    if ww == "canal":
        return "canals"
    if tags.get("natural") == "water" or tags.get("water"):
        return "water_bodies"
    if tags.get("landuse") == "forest" or tags.get("natural") == "wood":
        return "forests"
    if tags.get("power") in ("line", "minor_line"):
        return "transmission_lines"
    return None


def _rings_to_site(rings: Sequence[Sequence[Tuple[float, float]]]):
    geoms = []
    for ring in rings:
        if not ring or len(ring) < 3:
            continue
        pts = [(float(lon), float(lat)) for lat, lon in ring]
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        geom = Polygon(pts)
        if not geom.is_valid:
            geom = geom.buffer(0)
        if not geom.is_empty:
            geoms.append(geom)
    if not geoms:
        return None
    return unary_union(geoms)


def _feature_collection(features: List[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def fetch_site_constraints(
    rings: Sequence[Sequence[Tuple[float, float]]],
    *,
    timeout_sec: int = 90,
) -> Dict[str, Any]:
    """
    Query OSM for constraint features inside the site polygon.

    Returns categorized GeoJSON FeatureCollections and raw feature counts.
    """
    site = _rings_to_site(rings)
    if site is None:
        return {"success": False, "error": "Invalid site boundary"}

    query = build_site_constraint_query(rings, timeout_sec=timeout_sec)
    try:
        elements = overpass_query(query, timeout_sec=timeout_sec)
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "source": "OpenStreetMap Overpass",
        }

    buckets: Dict[str, List[dict]] = {k: [] for k in LAYER_STYLES}
    counts: Dict[str, int] = {k: 0 for k in LAYER_STYLES}

    for el in elements:
        if el.get("type") != "way":
            continue
        tags = el.get("tags") or {}
        category = _categorize(tags)
        if not category:
            continue
        geom = _way_geom(el)
        if geom is None:
            continue
        try:
            clipped = geom.intersection(site.buffer(0.001))
        except Exception:
            clipped = geom
        if clipped.is_empty:
            continue
        counts[category] += 1
        buckets[category].append(
            {
                "type": "Feature",
                "properties": {
                    "category": category,
                    "name": tags.get("name") or tags.get("ref") or "",
                    "osm_id": el.get("id"),
                    **{k: v for k, v in tags.items() if k in ("highway", "railway", "building", "waterway", "voltage")},
                },
                "geometry": mapping(clipped),
            }
        )

    layers = {cat: _feature_collection(feats) for cat, feats in buckets.items() if feats}
    return {
        "success": True,
        "source": "OpenStreetMap Overpass",
        "feature_counts": counts,
        "layers": layers,
        "disclaimer": (
            "Constraint features from OpenStreetMap — coverage varies by region. "
            "Setbacks are engineering assumptions; verify against local codes and surveys."
        ),
    }
