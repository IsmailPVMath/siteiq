"""Detailed LayoutIQ geometry for web preview and CAD export."""

from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Tuple

from layoutiq.coords import xy_to_latlon
from layoutiq.engine import run_layout

try:
    import ezdxf

    HAS_EZDXF = True
except ImportError:
    HAS_EZDXF = False


def _config_from_key(config_key: str) -> Tuple[int, bool, str]:
    match = re.match(r"^(FT|SAT)_(\d)P$", (config_key or "").strip().upper())
    if not match:
        raise ValueError("config_key must be like FT_1P, FT_2P, FT_3P, FT_4P, SAT_1P, or SAT_2P")
    prefix, n_raw = match.groups()
    n_portrait = int(n_raw)
    tracker = prefix == "SAT"
    if tracker and n_portrait not in (1, 2):
        raise ValueError("Tracker layouts currently support SAT_1P and SAT_2P")
    if not tracker and n_portrait not in (1, 2, 3, 4):
        raise ValueError("Fixed Tilt layouts currently support FT_1P to FT_4P")
    label = "Single-Axis Tracker" if tracker else "Fixed Tilt"
    return n_portrait, tracker, f"{label} — {n_portrait}P"


def _ring_xy_to_lonlat(poly: Any, ref_lat: float, ref_lon: float) -> List[List[float]]:
    coords = list(poly.exterior.coords)
    latlons = xy_to_latlon(coords, ref_lat, ref_lon)
    return [[round(lon, 8), round(lat, 8)] for lat, lon in latlons]


def _polygon_feature(poly: Any, ref_lat: float, ref_lon: float, props: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {
            "type": "Polygon",
            "coordinates": [_ring_xy_to_lonlat(poly, ref_lat, ref_lon)],
        },
    }


def build_layout_detail(
    boundary: List[List[float]],
    *,
    config_key: str,
    pitch_m: float,
    module_h: float = 2.094,
    module_w: float = 1.038,
    module_wp: int = 550,
    setback_m: float = 5.0,
    azimuth: float = 180.0,
) -> Dict[str, Any]:
    n_portrait, tracker, label = _config_from_key(config_key)
    layout = run_layout(
        boundary,
        module_h=module_h,
        module_w=module_w,
        n_portrait=n_portrait,
        pitch=pitch_m,
        setback=setback_m,
        azimuth=azimuth,
        mounting_type="sat" if tracker else "fixed_tilt",
    )
    if not layout:
        raise ValueError("No layout rows fit for this configuration and pitch")

    dc_kwp = round(layout["total_modules"] * module_wp / 1000, 1)
    ref_lat = layout["ref_lat"]
    ref_lon = layout["ref_lon"]
    features: List[Dict[str, Any]] = [
        _polygon_feature(layout["poly_m"], ref_lat, ref_lon, {"kind": "site_boundary"}),
        _polygon_feature(layout["poly_inset"], ref_lat, ref_lon, {"kind": "setback_inset"}),
    ]
    for idx, poly in enumerate(layout["rows_polys"], start=1):
        row_data = layout["rows_data"][idx - 1]
        features.append(
            _polygon_feature(
                poly,
                ref_lat,
                ref_lon,
                {
                    "kind": "pv_row",
                    "row_index": idx,
                    "n_modules": row_data["n_modules"],
                    "length_m": row_data["length_m"],
                },
            )
        )

    return {
        "config_key": config_key,
        "label": label,
        "mount_type": "Single-Axis Tracker" if tracker else "Fixed Tilt",
        "n_portrait": n_portrait,
        "pitch_m": pitch_m,
        "gcr": round(layout["row_ns"] / pitch_m, 3),
        "total_modules": layout["total_modules"],
        "total_rows": layout["total_rows"],
        "area_ha": layout["area_ha"],
        "dc_kwp": dc_kwp,
        "ref_lat": ref_lat,
        "ref_lon": ref_lon,
        "layout": layout,
        "geojson": {
            "type": "FeatureCollection",
            "features": features,
        },
    }


def _add_polyline(msp: Any, poly: Any, layer: str) -> None:
    if poly.is_empty:
        return
    if poly.geom_type == "Polygon":
        msp.add_lwpolyline(list(poly.exterior.coords), close=True, dxfattribs={"layer": layer})
    elif poly.geom_type in ("MultiPolygon", "GeometryCollection"):
        for geom in poly.geoms:
            if hasattr(geom, "exterior"):
                _add_polyline(msp, geom, layer)


def export_layout_dxf(detail: Dict[str, Any], project_name: str = "LayoutIQ") -> bytes:
    if not HAS_EZDXF:
        raise RuntimeError("ezdxf is not installed")

    layout = detail["layout"]
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6  # meters
    msp = doc.modelspace()
    doc.layers.add("SITE_BOUNDARY", color=5)
    doc.layers.add("SETBACK_INSET", color=8)
    doc.layers.add("PV_ROWS", color=3)
    doc.layers.add("LABELS", color=7)

    _add_polyline(msp, layout["poly_m"], "SITE_BOUNDARY")
    _add_polyline(msp, layout["poly_inset"], "SETBACK_INSET")
    for poly in layout["rows_polys"]:
        _add_polyline(msp, poly, "PV_ROWS")

    summary = (
        f"{project_name} | {detail['label']} | Pitch {detail['pitch_m']} m | "
        f"GCR {detail['gcr']} | {detail['total_modules']} modules | {detail['dc_kwp']} kWp"
    )
    minx, miny, _maxx, maxy = layout["poly_m"].bounds
    msp.add_text(summary, height=2.5, dxfattribs={"layer": "LABELS"}).set_placement((minx, maxy + 5))
    msp.add_text(
        f"Local metric coordinates. Reference WGS84 centroid: {detail['ref_lat']:.8f}, {detail['ref_lon']:.8f}",
        height=2.0,
        dxfattribs={"layer": "LABELS"},
    ).set_placement((minx, maxy + 2))

    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")
