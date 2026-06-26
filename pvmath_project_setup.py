"""Project Setup validation and versioned project_data helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

PROJECT_SETUP_SCHEMA_VERSION = 1

DEFAULT_MODULE = {
    "module_h": 2.094,
    "module_w": 1.038,
    "module_wp": 550,
    "modules_per_string": 28,
    "inter_string_gap_m": 0.5,
    "tracker_string_options": [8, 7, 6, 5],
    "max_tracker_length_m": 260.0,
    "exclude_tracker_slope": False,
    "tracker_slope_limit_pct": 6.0,
    "road_mode": "off",
    "road_preset": "no_roads",
    "rows_per_block": 0,
    "block_gap_m": 0.0,
}


def _has_boundary(data: dict[str, Any]) -> bool:
    site = data.get("site_boundary_geojson")
    if site:
        return True
    workflow = data.get("workflow") or {}
    return bool(workflow.get("parcels"))


def validate_project_data(data: dict[str, Any]) -> dict[str, Any]:
    """Validate setup payload and return readiness summary."""
    issues: list[dict[str, str]] = []
    name = (data.get("name") or data.get("project_info", {}).get("name") or "").strip()
    if not name:
        issues.append({"level": "error", "field": "name", "message": "Project name is required."})

    country = (data.get("country") or data.get("location", {}).get("country") or "").strip()
    if not country:
        issues.append({"level": "warning", "field": "country", "message": "Country not set — will infer from location if possible."})

    center = data.get("center") or data.get("location") or {}
    lat = center.get("lat")
    lon = center.get("lon")
    if lat is None or lon is None:
        issues.append({"level": "error", "field": "location", "message": "Site location (lat/lon) is required."})
    elif not (-90 <= float(lat) <= 90 and -180 <= float(lon) <= 180):
        issues.append({"level": "error", "field": "location", "message": "Coordinates are out of range."})

    workflow = data.get("workflow") or {}
    area_ha = workflow.get("area_ha") or data.get("geometry", {}).get("gross_area_ha")
    if area_ha is not None and float(area_ha) <= 0:
        issues.append({"level": "error", "field": "area_ha", "message": "Gross area must be positive."})
    if area_ha is not None and float(area_ha) > 100_000:
        issues.append({"level": "warning", "field": "area_ha", "message": "Project area is unusually large — verify boundary."})
    if area_ha is not None and 0 < float(area_ha) < 0.1:
        issues.append({"level": "warning", "field": "area_ha", "message": "Project area is very small — verify boundary."})

    has_boundary = _has_boundary(data)
    if not has_boundary:
        issues.append({
            "level": "warning",
            "field": "boundary",
            "message": "No site boundary — only SiteIQ screening will run. TerrainIQ, LayoutIQ, and YieldIQ need a boundary.",
        })

    readiness = {
        "has_boundary": has_boundary,
        "can_run_siteiq": bool(name and lat is not None and lon is not None),
        "can_run_terrainiq": has_boundary,
        "can_run_layoutiq": has_boundary,
        "can_run_yieldiq": has_boundary,
    }
    modules = ["SiteIQ"]
    if has_boundary:
        modules.extend(["TerrainIQ", "LayoutIQ", "YieldIQ"])

    errors = [i for i in issues if i["level"] == "error"]
    return {
        "valid": len(errors) == 0,
        "issues": issues,
        "readiness": readiness,
        "modules_to_run": modules,
    }


def merge_project_data(existing: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge patch into existing project_data without dropping omitted keys."""
    merged = deepcopy(existing or {})
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_project_data(merged[key], value)
        else:
            merged[key] = value
    merged["schema_version"] = PROJECT_SETUP_SCHEMA_VERSION
    return merged


def normalize_legacy_project_data(data: dict[str, Any]) -> dict[str, Any]:
    """Map legacy flat project_data to versioned structure while keeping compatibility."""
    if data.get("schema_version"):
        return data
    workflow = data.get("workflow") or {}
    assumptions = {**DEFAULT_MODULE}
    for k in DEFAULT_MODULE:
        if k in workflow:
            assumptions[k] = workflow[k]
    return {
        "schema_version": PROJECT_SETUP_SCHEMA_VERSION,
        "name": data.get("name", "New project"),
        "center": data.get("center", {}),
        "country": data.get("country", ""),
        "land_use": data.get("land_use", "Standard"),
        "mount_type": data.get("mount_type", "Fixed Tilt"),
        "site_boundary_geojson": data.get("site_boundary_geojson"),
        "restriction_polygons_geojson": data.get("restriction_polygons_geojson"),
        "buildable_area_geojson": data.get("buildable_area_geojson"),
        "project_info": {
            "name": data.get("name", "New project"),
            "client": workflow.get("client", ""),
            "notes": workflow.get("notes", ""),
        },
        "location": {
            "country": data.get("country", ""),
            "state": workflow.get("state", ""),
            "city": workflow.get("city", ""),
            "lat": (data.get("center") or {}).get("lat"),
            "lon": (data.get("center") or {}).get("lon"),
        },
        "geometry": {
            "gross_area_ha": workflow.get("area_ha"),
            "buildable_area_ha": workflow.get("buildable_area_ha"),
        },
        "design_basis": {
            "land_use": data.get("land_use", "Standard"),
            "mount_type": data.get("mount_type", "Fixed Tilt"),
            "target_capacity_mwp": workflow.get("target_capacity_mwp"),
            "target_cod": workflow.get("target_cod", ""),
            "currency": workflow.get("currency", "EUR"),
            "coordinate_system": workflow.get("coordinate_system", "WGS84"),
            "engineering_standard": workflow.get("engineering_standard", ""),
            "design_standard": workflow.get("design_standard", ""),
            "units": workflow.get("units", "metric"),
        },
        "assumptions": assumptions,
        "workflow": workflow,
    }
