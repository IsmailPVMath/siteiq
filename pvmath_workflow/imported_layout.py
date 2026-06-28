"""Build LayoutIQ detail / GeoJSON from imported DXF geometry."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from layoutiq.dxf_import import parse_layout_dxf
from layoutiq.tracker_units import build_tracker_unit_polys
from pvmath_workflow.layout_detail import _config_from_key, _polygon_feature


def _layout_to_geojson(layout: dict[str, Any], ref_lat: float, ref_lon: float) -> Dict[str, Any]:
    features: List[Dict[str, Any]] = []
    features.append(
        _polygon_feature(layout["poly_m"], ref_lat, ref_lon, {"kind": "site_boundary"})
    )
    features.append(
        _polygon_feature(layout["poly_inset"], ref_lat, ref_lon, {"kind": "buildable_parcel"})
    )

    unit_polys = layout.get("tracker_unit_polys") or build_tracker_unit_polys(layout)
    for unit in unit_polys:
        style = unit.get("style") or {}
        features.append(
            _polygon_feature(
                unit["poly"],
                ref_lat,
                ref_lon,
                {
                    "kind": "tracker_unit",
                    "unit_strings": unit["unit_strings"],
                    "unit_label": style.get("label", f"{unit['unit_strings']}S"),
                    "fill": style.get("fill"),
                    "stroke": style.get("stroke"),
                    "row_index": unit.get("row_index"),
                    "unit_index": unit.get("unit_index"),
                },
            )
        )

    for s_idx, spoly in enumerate(layout.get("string_polys") or []):
        features.append(
            _polygon_feature(
                spoly,
                ref_lat,
                ref_lon,
                {
                    "kind": "pv_module",
                    "string_index": s_idx + 1,
                    "modules_per_string": layout.get("modules_per_string", 28),
                    "n_modules": layout.get("modules_per_string", 28),
                },
            )
        )

    return {"type": "FeatureCollection", "features": features}


def build_imported_layout_detail(
    dxf_bytes: bytes,
    *,
    config_key: str,
    pitch_m: float,
    ref_lat: float,
    ref_lon: float,
    module_wp: int = 550,
    modules_per_string: int = 28,
    tracker_string_options: Optional[List[int]] = None,
    project_name: str = "Imported layout",
) -> Dict[str, Any]:
    """Parse DXF → PVMath layout detail (GeoJSON + counts for YieldIQ / BOM / A3)."""
    n_portrait, tracker, label = _config_from_key(config_key)
    layout = parse_layout_dxf(
        dxf_bytes,
        modules_per_string=modules_per_string,
        tracker_string_options=tracker_string_options,
    )
    if not layout.get("tracker_unit_polys"):
        layout["tracker_unit_polys"] = build_tracker_unit_polys(layout)

    total_modules = layout["total_modules"]
    dc_kwp = round(total_modules * module_wp / 1000, 1)
    row_ns = 2.094 * n_portrait if tracker else 2.094 * n_portrait
    gcr = round(row_ns / pitch_m, 3) if pitch_m > 0 else 0.0

    return {
        "config_key": config_key,
        "label": label,
        "mount_type": "Single-Axis Tracker" if tracker else "Fixed Tilt",
        "n_portrait": n_portrait,
        "pitch_m": pitch_m,
        "gcr": gcr,
        "total_modules": total_modules,
        "total_strings": layout.get("total_strings", 0),
        "total_tracker_units": layout.get("total_tracker_units", 0),
        "total_rows": layout.get("total_rows", 0),
        "area_ha": layout.get("area_ha", 0),
        "dc_kwp": dc_kwp,
        "dc_mwp": round(dc_kwp / 1000, 3),
        "mw_per_ha": round(dc_kwp / 1000 / layout["area_ha"], 3) if layout.get("area_ha") else None,
        "ref_lat": ref_lat,
        "ref_lon": ref_lon,
        "imported_from_dxf": True,
        "project_name": project_name,
        "layouts": [layout],
        "geojson": _layout_to_geojson(layout, ref_lat, ref_lon),
    }
