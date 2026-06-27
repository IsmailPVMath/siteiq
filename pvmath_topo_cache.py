"""TerrainIQ → SiteIQ confirmed terrain cache (Option B)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable, Optional


def boundary_fingerprint_from_boundaries(boundaries: list) -> str:
    """Hash enabled boundary rings (Project Setup format: lon, lat coords)."""
    parts = []
    for b in sorted(boundaries, key=lambda x: str(x.get("id", ""))):
        if not b.get("enabled", True):
            continue
        coords = b.get("coords") or []
        if len(coords) < 3:
            continue
        ring = [[round(float(c[0]), 6), round(float(c[1]), 6)] for c in coords]
        parts.append({"id": str(b.get("id", "")), "coords": ring})
    if not parts:
        return ""
    payload = json.dumps(parts, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def boundary_fingerprint_from_project(project: dict) -> str:
    if not project:
        return ""
    if project.get("polygon_boundaries"):
        return boundary_fingerprint_from_boundaries(project["polygon_boundaries"])
    pc = project.get("polygon_coords")
    if project.get("mode") == "full" and pc and len(pc) >= 3:
        return boundary_fingerprint_from_boundaries([{
            "id": "proj_0",
            "enabled": True,
            "coords": pc,
        }])
    return ""


def fingerprint_from_latlon_polys(polys: list) -> str:
    """Hash analysis polygons as [[lat, lon], ...] rings (TerrainIQ run boundary)."""
    parts = []
    for poly in polys:
        if not poly or len(poly) < 3:
            continue
        ring = [[round(float(p[1]), 6), round(float(p[0]), 6)] for p in poly]
        parts.append(ring)
    if not parts:
        return ""
    payload = json.dumps(parts, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def build_topo_cache(
    *,
    project_row_id,
    analysis_mode: str,
    boundary_fp: str,
    area_ha: float,
    lat_c: float,
    lon_c: float,
    grid_m: float,
    grid_points: int,
    mean_slope: float,
    max_slope: float,
    pct_over5: float,
    pct_over10: float,
    z_min: float,
    z_max: float,
    center_elev: float,
    extras: Optional[dict] = None,
    dem_zoom: Optional[int] = None,
) -> dict:
    return {
        "project_row_id": project_row_id,
        "analysis_mode": analysis_mode,
        "boundary_fp": boundary_fp,
        "area_ha": round(float(area_ha), 2),
        "lat_c": lat_c,
        "lon_c": lon_c,
        "grid_m": float(grid_m),
        "grid_points": int(grid_points),
        "mean_slope_pct": round(float(mean_slope), 2),
        "max_slope_pct": round(float(max_slope), 2),
        "pct_over5": round(float(pct_over5), 2),
        "pct_over10": round(float(pct_over10), 2),
        "z_min": round(float(z_min), 1),
        "z_max": round(float(z_max), 1),
        "center_elev": round(float(center_elev), 1),
        "elevation_range": round(float(z_max - z_min), 1),
        "extras": dict(extras or {}),
        "dem_zoom": dem_zoom,
        "run_at": datetime.now(timezone.utc).isoformat(),
    }


def get_topo_cache(session_state, project: dict) -> Optional[dict]:
    cache = (
        session_state.get("terrainiq_run_cache")
        or session_state.get("topoiq_run_cache")
        or (project or {}).get("terrainiq_cache")
        or (project or {}).get("topoiq_cache")
    )
    if isinstance(cache, dict) and cache.get("mean_slope_pct") is not None:
        return cache
    return None


def topo_cache_valid_for_siteiq(
    cache: dict,
    project: dict,
    project_row_id=None,
) -> bool:
    if not cache or cache.get("analysis_mode") != "parcels":
        return False
    fp = boundary_fingerprint_from_project(project)
    if not fp or cache.get("boundary_fp") != fp:
        return False
    cached_row = cache.get("project_row_id")
    if project_row_id and cached_row and str(cached_row) != str(project_row_id):
        return False
    return True


def terrain_from_topo_cache(cache: dict) -> dict:
    """SiteIQ-compatible terrain dict from a TerrainIQ run cache."""
    return {
        "success": True,
        "terrainiq_confirmed": True,
        "topoiq_confirmed": True,  # legacy alias for saved project payloads
        "boundary_sampled": False,
        "center_elev": cache.get("center_elev"),
        "mean_slope_pct": cache.get("mean_slope_pct"),
        "max_slope_pct": cache.get("max_slope_pct"),
        "elevation_range": cache.get("elevation_range"),
        "sample_points": cache.get("grid_points", 0),
        "grid_m": cache.get("grid_m"),
        "pct_over5": cache.get("pct_over5"),
        "pct_over10": cache.get("pct_over10"),
        "extras": cache.get("extras") or {},
        "dem_zoom": cache.get("dem_zoom"),
        "run_at": cache.get("run_at"),
    }


def resolve_terrain_for_siteiq(
    lat: float,
    lon: float,
    *,
    polygons,
    project: dict,
    project_row_id,
    session_state,
    fetch_sparse: Callable,
) -> tuple[dict, bool]:
    """Return (terrain_dict, used_topo_cache)."""
    cache = get_topo_cache(session_state, project)
    if cache and topo_cache_valid_for_siteiq(cache, project, project_row_id):
        return terrain_from_topo_cache(cache), True
    return fetch_sparse(lat, lon, polygons=polygons), False


def persist_topo_cache(cache: dict, session_state, *, user_id: str = "", save_fn=None) -> None:
    session_state["terrainiq_run_cache"] = cache
    proj = dict(session_state.get("pvm_project") or {})
    proj["terrainiq_cache"] = cache
    session_state["pvm_project"] = proj
    row_id = session_state.get("pvm_project_row_id")
    if user_id and row_id and save_fn:
        save_fn(user_id, proj, row_id=row_id)
