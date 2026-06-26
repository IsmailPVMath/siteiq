"""Compute buildable area from site boundary, GIS constraints, and configurable setbacks."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from pvmath_workflow.gis_constraints import DEFAULT_SETBACKS_M, LAYER_STYLES


def _meters_to_deg(meters: float, lat: float) -> float:
    """Approximate degree buffer at latitude (adequate for site-scale polygons)."""
    m_per_deg = 111_320.0 * max(0.2, abs(math.cos(math.radians(lat))))
    return meters / m_per_deg


def _area_ha(geom, lat: float) -> float:
    if geom is None or geom.is_empty:
        return 0.0
    return (geom.area * (111_320.0**2) * abs(math.cos(math.radians(lat)))) / 10_000.0


def _rings_to_site(rings: Sequence[Sequence[Tuple[float, float]]]):
    from shapely.geometry import Polygon

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


def _buffer_geom(geom, meters: float, lat: float):
    if geom is None or geom.is_empty or meters <= 0:
        return geom
    deg = _meters_to_deg(meters, lat)
    out = geom.buffer(deg)
    if not out.is_valid:
        out = out.buffer(0)
    return out


def _fc_to_geoms(fc: dict) -> List[Any]:
    geoms = []
    if not fc or fc.get("type") != "FeatureCollection":
        return geoms
    for feat in fc.get("features") or []:
        try:
            g = shape(feat.get("geometry"))
            if not g.is_empty:
                geoms.append(g)
        except Exception:
            continue
    return geoms


def compute_buildable_area(
    rings: Sequence[Sequence[Tuple[float, float]]],
    constraint_layers: Dict[str, dict],
    *,
    setbacks_m: Optional[Dict[str, float]] = None,
    manual_restrictions_geojson: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Apply setbacks and subtract constraint zones from the site polygon.

    Returns buildable GeoJSON, excluded union, per-category stats, and percentages.
    """
    site = _rings_to_site(rings)
    if site is None:
        return {"success": False, "error": "Invalid site boundary"}

    lat = float(site.centroid.y)
    setbacks = {**DEFAULT_SETBACKS_M, **(setbacks_m or {})}
    site_area_ha = round(_area_ha(site, lat), 2)

    work = site
    boundary_setback = setbacks.get("site_boundary", 0.0)
    if boundary_setback > 0:
        work = _buffer_geom(site, -boundary_setback, lat)
        if work is None or work.is_empty:
            return {
                "success": True,
                "site_area_ha": site_area_ha,
                "buildable_area_ha": 0.0,
                "buildable_pct": 0.0,
                "buildable_area_geojson": None,
                "excluded_area_geojson": mapping(site),
                "constraint_summary": [],
                "setbacks_m": setbacks,
                "note": "Site boundary setback consumes entire polygon.",
            }

    exclusions: List[Any] = []
    summary: List[dict] = []

    for category, fc in (constraint_layers or {}).items():
        setback = setbacks.get(category, 0.0)
        if setback <= 0:
            continue
        geoms = _fc_to_geoms(fc)
        if not geoms:
            continue
        union = unary_union(geoms)
        buffered = _buffer_geom(union, setback, lat)
        if buffered is None or buffered.is_empty:
            continue
        try:
            clipped = buffered.intersection(site)
        except Exception:
            clipped = buffered
        if clipped.is_empty:
            continue
        exclusions.append(clipped)
        summary.append(
            {
                "category": category,
                "label": category.replace("_", " ").title(),
                "feature_count": len(geoms),
                "setback_m": setback,
                "excluded_ha": round(_area_ha(clipped, lat), 2),
                "style": LAYER_STYLES.get(category, {}),
            }
        )

    if manual_restrictions_geojson:
        manual = _parse_geojson_geom(manual_restrictions_geojson)
        if manual is not None and not manual.is_empty:
            exclusions.append(manual)
            summary.append(
                {
                    "category": "manual",
                    "label": "Manual restrictions",
                    "feature_count": 1,
                    "setback_m": 0.0,
                    "excluded_ha": round(_area_ha(manual.intersection(site), lat), 2),
                    "style": {"color": "#f59e0b", "fillColor": "#fcd34d"},
                }
            )

    excluded_union = unary_union(exclusions) if exclusions else None
    buildable = work if excluded_union is None else work.difference(excluded_union)
    if not buildable.is_valid:
        buildable = buildable.buffer(0)
    if buildable.is_empty:
        buildable_geo = None
        buildable_ha = 0.0
    else:
        buildable_geo = mapping(buildable)
        buildable_ha = round(_area_ha(buildable, lat), 2)

    excluded_geo = mapping(excluded_union) if excluded_union is not None and not excluded_union.is_empty else None
    pct = round((buildable_ha / site_area_ha) * 100, 1) if site_area_ha > 0 else 0.0

    return {
        "success": True,
        "site_area_ha": site_area_ha,
        "buildable_area_ha": buildable_ha,
        "buildable_pct": pct,
        "buildable_area_geojson": buildable_geo,
        "excluded_area_geojson": excluded_geo,
        "constraint_summary": sorted(summary, key=lambda x: -x["excluded_ha"]),
        "setbacks_m": setbacks,
    }


def _parse_geojson_geom(obj: dict):
    from shapely.geometry import GeometryCollection

    if not obj:
        return None
    if obj.get("type") == "FeatureCollection":
        geoms = []
        for feat in obj.get("features") or []:
            try:
                geoms.append(shape(feat.get("geometry")))
            except Exception:
                continue
        return unary_union(geoms) if geoms else None
    if obj.get("type") == "Feature":
        return shape(obj.get("geometry"))
    return shape(obj)
