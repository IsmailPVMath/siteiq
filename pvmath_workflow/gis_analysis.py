"""SiteIQ intelligent GIS analysis — constraints + buildable area orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pvmath_workflow.buildable_engine import compute_buildable_area
from pvmath_workflow.gis_constraints import DEFAULT_SETBACKS_M, LAYER_STYLES, fetch_site_constraints
from pvmath_workflow.grid import nearest_substation


@dataclass
class GisAnalysisRequest:
    boundary: List[Tuple[float, float]] = field(default_factory=list)  # (lat, lon)
    boundaries: List[List[Tuple[float, float]]] = field(default_factory=list)
    restriction_polygons_geojson: Optional[dict] = None
    setbacks_m: Optional[Dict[str, float]] = None
    include_grid: bool = True


def _normalize_rings(req: GisAnalysisRequest) -> List[List[Tuple[float, float]]]:
    rings: List[List[Tuple[float, float]]] = []
    for ring in req.boundaries:
        pts = [(float(p[0]), float(p[1])) for p in ring if len(p) >= 2]
        if len(pts) >= 3:
            rings.append(pts)
    if not rings and req.boundary and len(req.boundary) >= 3:
        rings.append([(float(lat), float(lon)) for lat, lon in req.boundary])
    return rings


def run_gis_analysis(req: GisAnalysisRequest) -> Dict[str, Any]:
    rings = _normalize_rings(req)
    if not rings:
        return {"success": False, "error": "Site boundary required (≥3 points)."}

    constraints = fetch_site_constraints(rings)
    if not constraints.get("success"):
        return constraints

    buildable = compute_buildable_area(
        rings,
        constraints.get("layers") or {},
        setbacks_m=req.setbacks_m,
        manual_restrictions_geojson=req.restriction_polygons_geojson,
    )
    if not buildable.get("success"):
        return buildable

    # Site centroid for grid / context
    clat = sum(p[0] for ring in rings for p in ring) / sum(len(r) for r in rings)
    clon = sum(p[1] for ring in rings for p in ring) / sum(len(r) for r in rings)

    grid = nearest_substation(clat, clon) if req.include_grid else None

    site_ring = rings[0]
    site_geojson = {
        "type": "Feature",
        "properties": {"category": "site_boundary"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[lon, lat] for lat, lon in (site_ring if site_ring[0] == site_ring[-1] else [*site_ring, site_ring[0]])]
            ],
        },
    }

    return {
        "success": True,
        "coordinates": {"lat": round(clat, 6), "lon": round(clon, 6)},
        "site_area_ha": buildable["site_area_ha"],
        "buildable_area_ha": buildable["buildable_area_ha"],
        "buildable_pct": buildable["buildable_pct"],
        "site_boundary_geojson": site_geojson,
        "buildable_area_geojson": buildable.get("buildable_area_geojson"),
        "excluded_area_geojson": buildable.get("excluded_area_geojson"),
        "constraint_layers": constraints.get("layers") or {},
        "layer_styles": LAYER_STYLES,
        "constraint_summary": buildable.get("constraint_summary") or [],
        "feature_counts": constraints.get("feature_counts") or {},
        "setbacks_m": buildable.get("setbacks_m") or DEFAULT_SETBACKS_M,
        "grid": grid,
        "sources": ["OpenStreetMap Overpass", "PVMath buildable engine"],
        "disclaimer": constraints.get("disclaimer", ""),
        "note": (
            "Terrain slope exclusions are computed separately in TopoIQ / LayoutIQ. "
            "This analysis uses mapped OSM features with configurable setbacks."
        ),
    }
