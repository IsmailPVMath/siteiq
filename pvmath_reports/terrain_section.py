"""TerrainIQ section for the unified PVMath report."""

from __future__ import annotations

import io
from typing import Any, Dict, List, Optional, Sequence, Tuple

from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Spacer

from pvmath_geocode import resolve_location_label
from pvmath_reports.common import base_styles, lp, module_divider, section_hdr
from pvmath_terrain_report import (
    build_report_context,
    build_terrain_unified_flowables,
    render_slope_map_png,
)
from pvmath_topo_engine import run_topo_analysis


def _boundaries_lonlat(boundaries: Sequence[Sequence[Any]]) -> List[List[Tuple[float, float]]]:
    rings: List[List[Tuple[float, float]]] = []
    for ring in boundaries or []:
        pts: List[Tuple[float, float]] = []
        for p in ring:
            if isinstance(p, dict):
                pts.append((float(p["lon"]), float(p["lat"])))
            else:
                pts.append((float(p[1]), float(p[0])))
        if len(pts) >= 3:
            rings.append(pts)
    return rings


def _try_slope_map_buf(
    boundaries: Optional[Sequence[Sequence[Any]]],
    topo: Dict[str, Any],
) -> Optional[io.BytesIO]:
    if not boundaries:
        return None
    try:
        polys = _boundaries_lonlat(boundaries)
        if not polys:
            return None
        analysis = run_topo_analysis(
            polys,
            grid_m=float(topo.get("grid_m_used") or 5),
            allow_coarsen=True,
        )
        bbox = analysis["bbox"]
        buf = render_slope_map_png(
            analysis["X"],
            analysis["Y"],
            analysis["Z"],
            float(analysis["grid_m_used"]),
            float(bbox["south"]),
            float(bbox["north"]),
            float(bbox["west"]),
            float(bbox["east"]),
            polygon_list=analysis["polygons"],
            terrain_source_used=str(analysis.get("terrain_source_used", "")),
            terrain_disclaimer=str((analysis.get("terrain_source") or {}).get("disclaimer", "")),
        )
        if not buf:
            return None
        out = io.BytesIO(buf.getvalue())
        out.seek(0)
        return out
    except Exception:
        return None


def topo_to_report_context(
    topo: Dict[str, Any],
    *,
    project_name: str,
    country: str,
    location_label: str,
    lat: float,
    lon: float,
    land_use: str,
    mount_type: str,
    slope_img_buf=None,
) -> dict:
    bbox = topo.get("bbox") or {}
    lat_c = float(bbox.get("lat_c", lat))
    lon_c = float(bbox.get("lon_c", lon))
    elev = topo.get("elevation") or {}
    slope = topo.get("slope") or {}
    vf = topo.get("verdict_fixed") or {}
    vt = topo.get("verdict_tracker") or {}
    ctx = build_report_context(
        project_name=project_name,
        country=country,
        location_label=location_label or resolve_location_label(lat_c, lon_c, country=country),
        lat_c=lat_c,
        lon_c=lon_c,
        area_ha=float(topo.get("area_ha") or 0),
        grid_spacing=float(topo.get("grid_m_used") or 5),
        grid_spacing_requested=float(topo.get("grid_m_requested") or topo.get("grid_m_used") or 5),
        z_min=float(elev.get("z_min", 0)),
        z_max=float(elev.get("z_max", 0)),
        mean_slope=float(slope.get("mean", 0)),
        max_slope=float(slope.get("max", 0)),
        pct_over5=float(slope.get("pct_over5", 0)),
        pct_over10=float(slope.get("pct_over10", 0)),
        slope_bins=slope.get("bins"),
        slope_img_buf=slope_img_buf,
        land_use=land_use,
        mount_type=mount_type,
        boundary_provenance="Workflow boundary",
        prepared_by="PVMath",
        module_confidence="Screening-grade terrain assessment.",
        extras=topo.get("extras") or {},
        terrain_source=topo.get("terrain_source") or {},
        terrain_source_used=str(topo.get("terrain_source_used", "copernicus_glo30")),
        siteiq_run_cache=None,
        dem_zoom=int(topo.get("dem_zoom") or 0),
    )
    if vf.get("label"):
        ctx["verdict_fixed"] = (vf.get("label", ""), vf.get("detail", ""))
    if vt.get("label"):
        ctx["verdict_tracker"] = (vt.get("label", ""), vt.get("detail", ""))
    if topo.get("terrain_drivers"):
        ctx["terrain_drivers"] = topo["terrain_drivers"]
    ctx["siteiq_note"] = ""
    return ctx


def build_terrain_section_flowables(
    topo: Optional[Dict[str, Any]],
    *,
    project_name: str,
    country: str,
    location_label: str,
    lat: float,
    lon: float,
    land_use: str,
    mount_type: str,
    boundaries: Optional[Sequence[Sequence[Any]]] = None,
    slope_img_png: Optional[bytes] = None,
) -> List:
    st = base_styles()
    if not topo:
        return [
            *module_divider(),
            section_hdr("TerrainIQ — Terrain analysis", st),
            Spacer(1, 4 * mm),
            lp("TerrainIQ not run — draw a site boundary and run terrain analysis.", st["muted"]),
        ]

    if slope_img_png:
        slope_buf = io.BytesIO(slope_img_png)
        slope_buf.seek(0)
    else:
        slope_buf = _try_slope_map_buf(boundaries, topo)
    ctx = topo_to_report_context(
        topo,
        project_name=project_name,
        country=country,
        location_label=location_label,
        lat=lat,
        lon=lon,
        land_use=land_use,
        mount_type=mount_type,
        slope_img_buf=slope_buf,
    )
    body = build_terrain_unified_flowables(
        ctx,
        accent="#157a40",
        header_bg="#e8f5ee",
        row_bg="#f5f7f5",
    )
    header = [section_hdr("TerrainIQ — Terrain analysis", st), Spacer(1, 3 * mm)]
    if body:
        return [
            *module_divider(),
            KeepTogether(header + [body[0]]),
            *body[1:],
        ]
    return [*module_divider(), *header, *body]
