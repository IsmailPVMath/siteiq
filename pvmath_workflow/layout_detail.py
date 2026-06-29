"""Detailed LayoutIQ geometry for web preview and CAD export."""

from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional, Tuple

from layoutiq.coords import xy_to_latlon
from layoutiq.defaults import layout_params
from layoutiq.engine import run_layout, site_layout_grid
from layoutiq.tracker_units import build_tracker_unit_polys

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


def _ring_xy_to_lonlat(ring: Any, ref_lat: float, ref_lon: float) -> List[List[float]]:
    coords = list(ring.coords)
    latlons = xy_to_latlon(coords, ref_lat, ref_lon)
    return [[round(lon, 8), round(lat, 8)] for lat, lon in latlons]


def _polygon_rings(poly: Any, ref_lat: float, ref_lon: float) -> List[List[List[float]]]:
    rings = [_ring_xy_to_lonlat(poly.exterior, ref_lat, ref_lon)]
    for interior in poly.interiors:
        rings.append(_ring_xy_to_lonlat(interior, ref_lat, ref_lon))
    return rings


def _geom_to_geojson(geom: Any, ref_lat: float, ref_lon: float) -> Optional[Dict[str, Any]]:
    """Convert a shapely polygonal geometry to a GeoJSON geometry.

    Handles Polygon, MultiPolygon and GeometryCollection (which can appear once
    setbacks/restrictions split the buildable area into several pieces).
    """
    if geom is None or getattr(geom, "is_empty", True):
        return None
    gtype = geom.geom_type
    if gtype == "Polygon":
        return {"type": "Polygon", "coordinates": _polygon_rings(geom, ref_lat, ref_lon)}
    if gtype in ("MultiPolygon", "GeometryCollection"):
        polys = [
            g
            for g in geom.geoms
            if getattr(g, "geom_type", "") == "Polygon" and not g.is_empty
        ]
        if not polys:
            return None
        if len(polys) == 1:
            return {"type": "Polygon", "coordinates": _polygon_rings(polys[0], ref_lat, ref_lon)}
        return {
            "type": "MultiPolygon",
            "coordinates": [_polygon_rings(p, ref_lat, ref_lon) for p in polys],
        }
    return None


def _polygon_feature(poly: Any, ref_lat: float, ref_lon: float, props: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "Feature",
        "properties": props,
        "geometry": _geom_to_geojson(poly, ref_lat, ref_lon),
    }


def _normalize_polys(
    boundary: Optional[List[List[float]]],
    boundaries: Optional[List[List[List[float]]]],
) -> List[List[List[float]]]:
    polys = [p for p in (boundaries or []) if p and len(p) >= 3]
    if not polys and boundary and len(boundary) >= 3:
        polys = [boundary]
    return polys


def build_layout_detail(
    boundary: Optional[List[List[float]]] = None,
    *,
    boundaries: Optional[List[List[List[float]]]] = None,
    restriction_polygons: Optional[List[List[List[float]]]] = None,
    config_key: str,
    pitch_m: float,
    module_h: float = 2.094,
    module_w: float = 1.038,
    module_wp: int = 550,
    setback_m: float = 5.0,
    azimuth: float = 180.0,
    modules_per_string: int = 28,
    inter_string_gap_m: float = 0.5,
    tracker_string_options: Optional[List[int]] = None,
    max_tracker_length_m: float = 260.0,
    rows_per_block: int = 0,
    block_gap_m: float = 0.0,
    ns_gap_1_m: float = 0.0,
    cols_per_block: int = 0,
    ew_gap_m: float = 0.0,
    road_mode: str = "off",
    road_preset: str = "no_roads",
    allow_partial_strings: bool = False,
    row_alignment: str = "horizontal",
    prune_isolated_blocks: bool = True,
    restriction_geojson: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    n_portrait, tracker, label = _config_from_key(config_key)
    polys = _normalize_polys(boundary, boundaries)
    restrictions = _normalize_polys(None, restriction_polygons)
    if not polys:
        raise ValueError("A site boundary is required")

    all_pts = [pt for poly in polys for pt in poly]
    ref_lat = sum(p[0] for p in all_pts) / len(all_pts)
    ref_lon = sum(p[1] for p in all_pts) / len(all_pts)

    lp = layout_params(
        module_h=module_h,
        module_w=module_w,
        module_wp=module_wp,
        modules_per_string=modules_per_string,
        inter_string_gap_m=inter_string_gap_m,
        tracker_string_options=tracker_string_options,
        max_tracker_length_m=max_tracker_length_m,
        rows_per_block=rows_per_block,
        block_gap_m=block_gap_m,
        ns_gap_1_m=ns_gap_1_m,
        cols_per_block=cols_per_block,
        ew_gap_m=ew_gap_m,
        road_mode=road_mode,  # type: ignore[arg-type]
        road_preset=road_preset,
    )

    layouts = []
    site_grid = site_layout_grid(
        polys,
        setback=setback_m,
        restriction_latlons=restrictions,
        ref_lat=ref_lat,
        ref_lon=ref_lon,
        pitch=pitch_m,
        azimuth=azimuth,
        is_tracker=tracker,
        restriction_geojson=restriction_geojson,
    )
    grid_kwargs: Dict[str, Any] = {}
    if site_grid:
        grid_kwargs = {
            "grid_y_origin": site_grid["grid_y_origin"],
            "south_fence_x": site_grid["south_fence_x"],
            "west_fence_x": site_grid["west_fence_x"],
            "rotate_origin": site_grid["rotate_origin"],
        }

    for poly in polys:
        layout = run_layout(
            poly,
            module_h=lp["module_h"],
            module_w=lp["module_w"],
            n_portrait=n_portrait,
            pitch=pitch_m,
            setback=setback_m,
            azimuth=azimuth,
            mounting_type="sat" if tracker else "fixed_tilt",
            modules_per_string=lp["modules_per_string"],
            inter_string_gap_m=lp["inter_string_gap_m"],
            tracker_string_options=lp["tracker_string_options"],
            max_tracker_length_m=lp["max_tracker_length_m"],
            rows_per_block=lp["rows_per_block"],
            block_gap_m=lp["block_gap_m"],
            ns_gap_1_m=lp["ns_gap_1_m"],
            restriction_latlons=restrictions,
            ref_lat=ref_lat,
            ref_lon=ref_lon,
            allow_partial_strings=allow_partial_strings,
            row_alignment=row_alignment,
            cols_per_block=lp["cols_per_block"],
            ew_gap_m=lp["ew_gap_m"],
            prune_isolated_blocks=prune_isolated_blocks,
            restriction_geojson=restriction_geojson,
            **grid_kwargs,
        )
        if layout:
            layout["tracker_unit_polys"] = build_tracker_unit_polys(layout)
            layouts.append(layout)
    if not layouts:
        raise ValueError("No layout rows fit for this configuration and pitch")

    features: List[Dict[str, Any]] = []
    row_index = 0
    string_index = 0
    total_modules = 0
    total_rows = 0
    total_strings = 0
    total_tracker_units = 0
    total_area_ha = 0.0
    for layout in layouts:
        row_index_base = row_index
        features.append(
            _polygon_feature(layout["poly_m"], ref_lat, ref_lon, {"kind": "site_boundary"})
        )
        features.append(
            _polygon_feature(
                layout["poly_inset"],
                ref_lat,
                ref_lon,
                {"kind": "buildable_parcel"},
            )
        )
        for s_idx, spoly in enumerate(layout.get("string_polys") or []):
            string_index += 1
            local_idxs = layout.get("string_row_local_idx") or []
            local_row_idx = local_idxs[s_idx] if s_idx < len(local_idxs) else 0
            features.append(
                _polygon_feature(
                    spoly,
                    ref_lat,
                    ref_lon,
                    {
                        "kind": "pv_module",
                        "string_index": string_index,
                        "modules_per_string": layout["modules_per_string"],
                        "n_modules": layout["modules_per_string"],
                        "row_index": row_index_base + local_row_idx + 1,
                    },
                )
            )
        for unit in layout.get("tracker_unit_polys") or []:
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
        rows_data = layout["rows_data"]
        for local_idx, poly in enumerate(layout["rows_polys"]):
            row_index += 1
            # A single row band can clip into a MultiPolygon on concave parcels,
            # so rows_polys may be longer than rows_data — clamp to stay aligned.
            if local_idx < len(rows_data):
                row_data = rows_data[local_idx]
            elif rows_data:
                row_data = rows_data[-1]
            else:
                row_data = {"n_modules": 0, "n_strings": 0, "tracker_units": [], "length_m": 0.0}
            features.append(
                _polygon_feature(
                    poly,
                    ref_lat,
                    ref_lon,
                    {
                        "kind": "pv_row",
                        "row_index": row_index,
                        "n_modules": row_data["n_modules"],
                        "partial_modules": row_data.get("partial_modules", 0),
                        "n_strings": row_data.get("n_strings", 0),
                        "tracker_units": row_data.get("tracker_units") or [],
                        "length_m": row_data["length_m"],
                    },
                )
            )
        total_modules += layout["total_modules"]
        total_rows += layout["total_rows"]
        total_strings += layout.get("total_strings", 0)
        total_tracker_units += layout.get("total_tracker_units", 0)
        total_area_ha += layout["area_ha"]

    dc_kwp = round(total_modules * module_wp / 1000, 1)
    dc_mwp = round(dc_kwp / 1000, 3)
    row_ns = layouts[0]["row_ns"]

    return {
        "config_key": config_key,
        "label": label,
        "mount_type": "Single-Axis Tracker" if tracker else "Fixed Tilt",
        "n_portrait": n_portrait,
        "pitch_m": pitch_m,
        "gcr": round(row_ns / pitch_m, 3),
        "total_modules": total_modules,
        "total_strings": total_strings,
        "total_tracker_units": total_tracker_units,
        "total_rows": total_rows,
        "area_ha": round(total_area_ha, 3),
        "dc_kwp": dc_kwp,
        "dc_mwp": dc_mwp,
        "mw_per_ha": round(dc_mwp / total_area_ha, 3) if total_area_ha else None,
        "layout_params": lp,
        "ref_lat": ref_lat,
        "ref_lon": ref_lon,
        "layouts": layouts,
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

    layouts = detail.get("layouts") or ([detail["layout"]] if detail.get("layout") else [])
    if not layouts:
        raise ValueError("No layout geometry to export")
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6  # meters
    msp = doc.modelspace()
    doc.layers.add("SITE_BOUNDARY", color=5)
    doc.layers.add("SETBACK_INSET", color=8)
    doc.layers.add("PV_MODULE", color=140)
    doc.layers.add("PV_ROWS", color=3)
    doc.layers.add("LABELS", color=7)

    from layoutiq.tracker_styles import TRACKER_UNIT_STYLES

    for n, style in TRACKER_UNIT_STYLES.items():
        doc.layers.add(style["dxf_layer"], color=style["dxf_color"])

    for layout in layouts:
        if not layout.get("tracker_unit_polys"):
            layout["tracker_unit_polys"] = build_tracker_unit_polys(layout)
        _add_polyline(msp, layout["poly_m"], "SITE_BOUNDARY")
        _add_polyline(msp, layout["poly_inset"], "SETBACK_INSET")
        for spoly in layout.get("string_polys") or []:
            _add_polyline(msp, spoly, "PV_MODULE")
        for unit in layout.get("tracker_unit_polys") or []:
            layer = (unit.get("style") or {}).get("dxf_layer", "PV_ROWS")
            _add_polyline(msp, unit["poly"], layer)
        if not layout.get("tracker_unit_polys"):
            for poly in layout.get("rows_polys") or []:
                _add_polyline(msp, poly, "PV_ROWS")

    summary = (
        f"{project_name} | {detail['label']} | Pitch {detail['pitch_m']} m | "
        f"GCR {detail['gcr']} | {detail['total_modules']} modules | {detail['dc_kwp']} kWp"
    )
    minx, miny, _maxx, maxy = layouts[0]["poly_m"].bounds
    msp.add_text(summary, height=2.5, dxfattribs={"layer": "LABELS"}).set_placement((minx, maxy + 5))
    msp.add_text(
        f"Local metric coordinates. Reference WGS84 centroid: {detail['ref_lat']:.8f}, {detail['ref_lon']:.8f}",
        height=2.0,
        dxfattribs={"layer": "LABELS"},
    ).set_placement((minx, maxy + 2))

    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")
