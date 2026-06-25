"""Site screening for unified workflow — no terrain slope (TopoIQ only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pvmath_capacity import format_mwp_range, format_mwh_range, screening_capacity
from pvmath_gate.screening import assess_regulatory, assess_solar, get_flood_risk
from pvmath_workflow.scoring import tier_score
from pvmath_yield import get_solar_data


def _pin_elevation_m(lat: float, lon: float) -> Optional[float]:
    """Single-point elevation for flood heuristic — not a terrain assessment."""
    from pvmath_gate.screening import _fetch_usgs_epqs_elevation, _fetch_opentopodata_elevations
    from pvmath_terrain_sources import TerrainSource, select_terrain_route

    route = select_terrain_route(lat, lon)
    headers = {"User-Agent": "PVMath/1.0 (pvmath.com; contact@pvmath.com)"}
    try:
        if route.source == TerrainSource.USGS_3DEP:
            return _fetch_usgs_epqs_elevation(lat, lon)
        if route.source == TerrainSource.COPERNICUS_EEA10:
            vals = _fetch_opentopodata_elevations([(lat, lon)], "eudem25m", headers, timeout=12)
            return vals[0] if vals else None
        vals = _fetch_opentopodata_elevations([(lat, lon)], "fabdem", headers, timeout=12)
        if vals and vals[0] is not None:
            return vals[0]
        vals = _fetch_opentopodata_elevations([(lat, lon)], "srtm30m", headers, timeout=12)
        return vals[0] if vals else None
    except Exception:
        return None


@dataclass
class WorkflowScreenRequest:
    project_name: str = "Site screening"
    lat: float = 0.0
    lon: float = 0.0
    area_ha: float = 0.0
    land_use: str = "Standard"
    mount_type: str = "Fixed Tilt"
    country: str = ""


@dataclass
class WorkflowScreenResponse:
    success: bool
    project_name: str
    coordinates: Dict[str, float]
    solar: Dict[str, Any] = field(default_factory=dict)
    flood: Dict[str, Any] = field(default_factory=dict)
    regulatory: Dict[str, Any] = field(default_factory=dict)
    capacity: Dict[str, Any] = field(default_factory=dict)
    score_components: Dict[str, int] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    terrain_note: str = (
        "Terrain slope is not assessed in site screening. "
        "Run TopoIQ on your site boundary for the authoritative terrain result and PVMath score."
    )


def run_workflow_screen(req: WorkflowScreenRequest) -> WorkflowScreenResponse:
    errors: List[str] = []
    mount = req.mount_type

    solar = get_solar_data(req.lat, req.lon, mount_type=mount)
    if not solar.get("success"):
        errors.append(solar.get("error", "Solar data unavailable"))

    solar_label, solar_detail = ("—", "—")
    if solar.get("success"):
        solar_label, solar_detail = assess_solar(float(solar["annual_ghi"]))

    center_elev = _pin_elevation_m(req.lat, req.lon)
    flood = get_flood_risk(req.lat, req.lon, center_elev)
    regulatory = assess_regulatory(req.lat, req.lon, req.land_use, req.country)

    yield_kwh = solar.get("annual_yield") if solar.get("success") else None
    cap = screening_capacity(req.area_ha, req.land_use, mount, yield_kwh)

    land_score = 80 if req.land_use == "Standard" else 72
    score_components = {
        "solar": tier_score(solar_label),
        "flood": tier_score(flood["risk"]),
        "land": land_score,
        "regulatory": 75,
    }

    return WorkflowScreenResponse(
        success=len(errors) == 0 or solar.get("success", False),
        project_name=req.project_name,
        coordinates={"lat": req.lat, "lon": req.lon},
        solar={
            "success": solar.get("success", False),
            "annual_ghi": solar.get("annual_ghi"),
            "annual_yield": solar.get("annual_yield"),
            "optimal_tilt": solar.get("optimal_tilt"),
            "rating": solar_label,
            "detail": solar_detail,
        },
        flood=flood,
        regulatory=regulatory,
        capacity={
            "mwp_range": format_mwp_range(cap.get("mwp_lo"), cap.get("mwp_hi")),
            "mwh_range": format_mwh_range(cap.get("mwh_lo"), cap.get("mwh_hi")),
            "mw_per_ha": cap.get("mw_per_ha"),
            "area_ha": req.area_ha,
        },
        score_components=score_components,
        errors=errors,
    )
