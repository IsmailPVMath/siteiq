"""TerrainIQ analysis, report, and export endpoints."""

from __future__ import annotations

import asyncio
import io
import os
from functools import partial
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from api.deps import get_current_user
from api.schemas.terrainiq import TerrainIQAnalyzeRequest, TerrainIQAnalyzeResponse
from pvmath_geocode import resolve_location_label
from pvmath_supabase import AuthUser, PLATFORM_APP, is_over_limit, usage_limit_detail
from pvmath_terrain_report import (
    build_report_context,
    generate_pdf_report,
    render_slope_map_png,
)
from pvmath_topo_engine import MAX_SITE_AREA_HA, boundaries_union_area_ha, run_topo_analysis
from pvmath_topo_export import (
    HAS_EZDXF,
    build_reference_json,
    build_topo_export_zip,
    epsg_utm_wgs84,
    export_dxf_contours,
    export_landxml_utm,
    export_linear_units,
    export_xyz_geo,
    export_xyz_georef,
    export_xyz_local,
    latlon_to_utm,
    local_en_from_latlon,
    sanitize_topo_basename,
    utm_grids_from_latlon,
)
from pvmath_yield import fetch_yield_cross_ref_bundle, yield_cross_ref_terrainiq_text

router = APIRouter(tags=["terrainiq"])

TOPO_APP = PLATFORM_APP
TOPO_TIMEOUT_SEC = int(os.environ.get("PVMATH_TOPO_TIMEOUT", "180"))


def _limit_detail(user: AuthUser) -> str:
    from pvmath_supabase import get_plan

    plan = get_plan(user.user_id, user.access_token) if user.access_token else "free"
    return usage_limit_detail(plan)


def _area_limit_message(area_ha: float) -> str:
    return (
        f"Site boundary is {area_ha:,.0f} ha — TerrainIQ supports up to {MAX_SITE_AREA_HA:,} ha. "
        "Draw or upload a smaller boundary, or split the site into sections."
    )


def _safe_name(value: str, fallback: str) -> str:
    raw = (value or fallback).strip().replace(" ", "_")
    return raw[:80] or fallback


def _normalize_point(raw: Any) -> Tuple[float, float]:
    if isinstance(raw, dict):
        if "lon" in raw and "lat" in raw:
            return float(raw["lon"]), float(raw["lat"])
        raise ValueError("Point object must include lat and lon")
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        return float(raw[0]), float(raw[1])
    raise ValueError("Point must be {lat, lon} or [lon, lat]")


def _normalize_polygons(raw_polygons: List[List[Any]]) -> List[List[Tuple[float, float]]]:
    if not raw_polygons:
        raise ValueError("polygons is required")
    polygons: List[List[Tuple[float, float]]] = []
    for ring in raw_polygons:
        if not isinstance(ring, list):
            raise ValueError("Each polygon ring must be a list")
        pts = [_normalize_point(p) for p in ring]
        if len(pts) < 3:
            raise ValueError("Each polygon ring requires at least 3 points")
        polygons.append(pts)
    return polygons


def _to_builtin(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _to_builtin(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_builtin(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.integer):
        return int(value)
    return value


def _run_topo(body: TerrainIQAnalyzeRequest) -> Dict[str, Any]:
    polygons = _normalize_polygons(body.polygons)
    area_ha = boundaries_union_area_ha(polygons)
    if area_ha > MAX_SITE_AREA_HA:
        raise ValueError(_area_limit_message(area_ha))
    return run_topo_analysis(
        polygons=polygons,
        grid_m=float(body.grid_m),
        allow_coarsen=body.allow_coarsen,
        contour_minor=float(body.contour_minor),
        contour_major=float(body.contour_major),
        mask_geojson=body.mask_geojson,
    )


def _analysis_response(body: TerrainIQAnalyzeRequest, analysis: Dict[str, Any]) -> TerrainIQAnalyzeResponse:
    terrain_source = _to_builtin(analysis["terrain_source"])
    slope = _to_builtin(analysis["slope"])
    elevation = _to_builtin(analysis["elevation"])
    extras = _to_builtin(analysis["extras"])
    terrain_drivers = _to_builtin(analysis["terrain_drivers"])
    return TerrainIQAnalyzeResponse(
        project_name=body.project_name,
        country=body.country,
        land_use=body.land_use,
        area_ha=float(analysis["area_ha"]),
        grid_m_requested=float(analysis["grid_m_requested"]),
        grid_m_used=float(analysis["grid_m_used"]),
        grid_points=int(analysis["grid_points"]),
        dem_zoom=int(analysis["dem_zoom"]),
        tile_count=int(analysis["tile_count"]),
        terrain_source_used=str(analysis["terrain_source_used"]),
        terrain_source=terrain_source,
        elevation=elevation,
        slope=slope,
        extras=extras,
        verdict_fixed=_to_builtin(analysis["verdict_fixed"]),
        verdict_tracker=_to_builtin(analysis["verdict_tracker"]),
        terrain_drivers=terrain_drivers,
        contour_minor=float(analysis["contours"]["minor_m"]),
        contour_major=float(analysis["contours"]["major_m"]),
        disclaimer=str(terrain_source.get("disclaimer", "Public DEM routing by region.")),
        bbox=_to_builtin(analysis["bbox"]),
        route_note=str(terrain_source.get("notes", "")) or None,
    )


def _build_topo_pdf(body: TerrainIQAnalyzeRequest, analysis: Dict[str, Any]) -> bytes:
    bbox = analysis["bbox"]
    X = analysis["X"]
    Y = analysis["Y"]
    Z = analysis["Z"]
    terrain_meta = analysis.get("terrain_source") or {}
    slope_img_buf = render_slope_map_png(
        X,
        Y,
        Z,
        float(analysis["grid_m_used"]),
        float(bbox["south"]),
        float(bbox["north"]),
        float(bbox["west"]),
        float(bbox["east"]),
        polygon_list=analysis["polygons"],
        terrain_source_used=str(analysis.get("terrain_source_used", "")),
        terrain_disclaimer=str(terrain_meta.get("disclaimer", "")),
    )
    slope_buf = io.BytesIO(slope_img_buf.getvalue()) if slope_img_buf else None
    if slope_buf:
        slope_buf.seek(0)
    yield_ref = fetch_yield_cross_ref_bundle(float(bbox["lat_c"]), float(bbox["lon_c"]))
    ctx = build_report_context(
        project_name=body.project_name,
        country=body.country,
        location_label=resolve_location_label(
            float(bbox["lat_c"]),
            float(bbox["lon_c"]),
            saved_label="",
            country=body.country,
        ),
        lat_c=float(bbox["lat_c"]),
        lon_c=float(bbox["lon_c"]),
        area_ha=float(analysis["area_ha"]),
        grid_spacing=float(analysis["grid_m_used"]),
        grid_spacing_requested=float(analysis["grid_m_requested"]),
        z_min=float(analysis["elevation"]["z_min"]),
        z_max=float(analysis["elevation"]["z_max"]),
        mean_slope=float(analysis["slope"]["mean"]),
        max_slope=float(analysis["slope"]["max"]),
        pct_over5=float(analysis["slope"]["pct_over5"]),
        pct_over10=float(analysis["slope"]["pct_over10"]),
        slope_bins=analysis["slope"]["bins"],
        slope_img_buf=slope_buf,
        land_use=body.land_use,
        mount_type=None,
        boundary_provenance="API boundary input",
        prepared_by="PVMath API",
        module_confidence="Screening-grade terrain assessment.",
        extras=analysis["extras"],
        siteiq_run_cache=None,
        project_row_id=None,
        dem_zoom=int(analysis["dem_zoom"]),
        terrain_source=analysis["terrain_source"],
        terrain_source_used=str(analysis["terrain_source_used"]),
        yield_cross_ref=yield_cross_ref_terrainiq_text(yield_ref),
    )
    pdf_bytes = generate_pdf_report(ctx)
    if not pdf_bytes:
        raise RuntimeError("PDF_GENERATION_FAILED")
    return pdf_bytes


@router.post("/terrainiq/analyze", response_model=TerrainIQAnalyzeResponse)
@router.post("/topoiq/analyze", response_model=TerrainIQAnalyzeResponse, include_in_schema=False)
async def analyze_terrainiq(
    body: TerrainIQAnalyzeRequest,
    user: AuthUser = Depends(get_current_user),
):
    if user.access_token and is_over_limit(user.user_id, TOPO_APP, user.access_token):
        raise HTTPException(status_code=429, detail=_limit_detail(user))

    loop = asyncio.get_running_loop()
    try:
        analysis = await asyncio.wait_for(
            loop.run_in_executor(None, partial(_run_topo, body)),
            timeout=TOPO_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"TerrainIQ analysis timed out after {TOPO_TIMEOUT_SEC}s. Try a smaller area or coarser grid.",
        )
    except ValueError as exc:
        detail = str(exc)
        if detail == "GRID_TOO_LARGE":
            raise HTTPException(
                status_code=422,
                detail=(
                    f"This boundary is too large for a {body.grid_m:.0f} m grid at full resolution. "
                    "Enable allow_coarsen, reduce area, or increase grid_m."
                ),
            )
        raise HTTPException(status_code=422, detail=detail)
    except RuntimeError as exc:
        detail = str(exc)
        if detail == "GRID_TOO_SMALL":
            raise HTTPException(status_code=422, detail="Boundary is too small for the selected grid spacing.")
        if detail == "NO_DATA_IN_BOUNDARY":
            raise HTTPException(status_code=422, detail="No elevation data inside boundary. Check polygon location.")
        if detail == "DEM_FETCH_FAILED":
            raise HTTPException(status_code=502, detail="Could not fetch terrain DEM tiles for this boundary.")
        raise HTTPException(status_code=500, detail=f"TerrainIQ analysis failed: {detail}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"TerrainIQ analysis failed: {exc}") from exc

    return _analysis_response(body, analysis)


def _render_slope_png(analysis: Dict[str, Any]) -> bytes:
    bbox = analysis["bbox"]
    terrain_meta = analysis.get("terrain_source") or {}
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
        terrain_disclaimer=str(terrain_meta.get("disclaimer", "")),
    )
    if buf is None:
        raise RuntimeError("SLOPE_MAP_UNAVAILABLE")
    return buf.getvalue()


@router.post("/terrainiq/slope-map")
@router.post("/topoiq/slope-map", include_in_schema=False)
async def terrainiq_slope_map(
    body: TerrainIQAnalyzeRequest,
    _user: AuthUser = Depends(get_current_user),
):
    loop = asyncio.get_running_loop()
    try:
        analysis = await asyncio.wait_for(
            loop.run_in_executor(None, partial(_run_topo, body)),
            timeout=TOPO_TIMEOUT_SEC,
        )
        png_bytes = await asyncio.wait_for(
            loop.run_in_executor(None, partial(_render_slope_png, analysis)),
            timeout=TOPO_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"TerrainIQ slope map timed out after {TOPO_TIMEOUT_SEC}s.",
        )
    except ValueError as exc:
        detail = str(exc)
        if detail == "GRID_TOO_LARGE":
            raise HTTPException(status_code=422, detail="Boundary too large for selected grid spacing.")
        raise HTTPException(status_code=422, detail=detail)
    except RuntimeError as exc:
        detail = str(exc)
        if detail == "SLOPE_MAP_UNAVAILABLE":
            raise HTTPException(
                status_code=503,
                detail="Slope map rendering is unavailable on this server (SciPy/Matplotlib missing).",
            )
        raise HTTPException(status_code=500, detail=f"TerrainIQ slope map failed: {detail}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"TerrainIQ slope map failed: {exc}") from exc

    return StreamingResponse(
        io.BytesIO(png_bytes),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/terrainiq/report-pdf")
@router.post("/topoiq/report-pdf", include_in_schema=False)
async def terrainiq_report_pdf(
    body: TerrainIQAnalyzeRequest,
    _user: AuthUser = Depends(get_current_user),
):
    loop = asyncio.get_running_loop()
    try:
        analysis = await asyncio.wait_for(
            loop.run_in_executor(None, partial(_run_topo, body)),
            timeout=TOPO_TIMEOUT_SEC,
        )
        pdf_bytes = await asyncio.wait_for(
            loop.run_in_executor(None, partial(_build_topo_pdf, body, analysis)),
            timeout=TOPO_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"TerrainIQ report generation timed out after {TOPO_TIMEOUT_SEC}s.",
        )
    except ValueError as exc:
        detail = str(exc)
        if detail == "GRID_TOO_LARGE":
            raise HTTPException(status_code=422, detail="Boundary too large for selected grid spacing.")
        raise HTTPException(status_code=422, detail=detail)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"TerrainIQ report generation failed: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"TerrainIQ report generation failed: {exc}") from exc

    safe = _safe_name(body.project_name, "terrainiq_report")
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe}_terrain_report.pdf"'},
    )


@router.post("/terrainiq/exports")
@router.post("/topoiq/exports", include_in_schema=False)
async def terrainiq_exports(
    body: TerrainIQAnalyzeRequest,
    _user: AuthUser = Depends(get_current_user),
):
    loop = asyncio.get_running_loop()
    try:
        analysis = await asyncio.wait_for(
            loop.run_in_executor(None, partial(_run_topo, body)),
            timeout=TOPO_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"TerrainIQ export preparation timed out after {TOPO_TIMEOUT_SEC}s.",
        )
    except ValueError as exc:
        detail = str(exc)
        if detail == "GRID_TOO_LARGE":
            raise HTTPException(status_code=422, detail="Boundary too large for selected grid spacing.")
        raise HTTPException(status_code=422, detail=detail)
    except RuntimeError as exc:
        detail = str(exc)
        if detail == "GRID_TOO_SMALL":
            raise HTTPException(status_code=422, detail="Boundary is too small for selected grid spacing.")
        if detail == "NO_DATA_IN_BOUNDARY":
            raise HTTPException(status_code=422, detail="No elevation data inside boundary.")
        if detail == "DEM_FETCH_FAILED":
            raise HTTPException(status_code=502, detail="Could not fetch terrain DEM tiles.")
        raise HTTPException(status_code=500, detail=f"TerrainIQ export preparation failed: {detail}")

    bbox = analysis["bbox"]
    X = analysis["X"]
    Y = analysis["Y"]
    Z = analysis["Z"]
    export_base = sanitize_topo_basename(body.project_name)
    cad_units = export_linear_units(body.country)

    try:
        pdf_bytes = await asyncio.wait_for(
            loop.run_in_executor(None, partial(_build_topo_pdf, body, analysis)),
            timeout=TOPO_TIMEOUT_SEC,
        )
        e_local, n_local = local_en_from_latlon(X, Y, float(bbox["lon_c"]), float(bbox["lat_c"]))
        e_georef, n_georef, _ = utm_grids_from_latlon(X, Y, float(bbox["lat_c"]), float(bbox["lon_c"]))
        lxml = export_landxml_utm(
            X,
            Y,
            Z,
            site_name=export_base,
            lat_c=float(bbox["lat_c"]),
            lon_c=float(bbox["lon_c"]),
            polygon_list=analysis["polygons"],
            units=cad_units,
        )
        xyz_local = export_xyz_local(X, Y, Z, float(bbox["lat_c"]), float(bbox["lon_c"]), units=cad_units)
        xyz_georef = export_xyz_georef(X, Y, Z, float(bbox["lat_c"]), float(bbox["lon_c"]), units=cad_units)
        xyz_geo = export_xyz_geo(X, Y, Z)
        ref_epsg = epsg_utm_wgs84(float(bbox["lat_c"]), float(bbox["lon_c"]))
        ref_utm_e, ref_utm_n, _ = latlon_to_utm(float(bbox["lat_c"]), float(bbox["lon_c"]))
        reference_json = build_reference_json(
            project_name=body.project_name,
            lat_c=float(bbox["lat_c"]),
            lon_c=float(bbox["lon_c"]),
            elev_c=float(analysis["elevation"]["center_elev"]),
            grid_m=float(analysis["grid_m_used"]),
            epsg=ref_epsg,
            utm_e=ref_utm_e,
            utm_n=ref_utm_n,
            parcel_count=len(analysis["polygons"]),
            analysis_mode="api",
            country=body.country,
            linear_units=cad_units,
        )
        dxf_local = None
        dxf_georef = None
        if HAS_EZDXF:
            dxf_local = export_dxf_contours(
                X,
                Y,
                Z,
                easting=e_local,
                northing=n_local,
                polygon_list=analysis["polygons"],
                lat_c=float(bbox["lat_c"]),
                lon_c=float(bbox["lon_c"]),
                minor_int=float(body.contour_minor),
                major_int=float(body.contour_major),
                georef=False,
                units=cad_units,
            )
            dxf_georef = export_dxf_contours(
                X,
                Y,
                Z,
                easting=e_georef,
                northing=n_georef,
                polygon_list=analysis["polygons"],
                lat_c=float(bbox["lat_c"]),
                lon_c=float(bbox["lon_c"]),
                minor_int=float(body.contour_minor),
                major_int=float(body.contour_major),
                georef=True,
                units=cad_units,
            )
        zip_bytes, _ = build_topo_export_zip(
            export_base,
            pdf_bytes=pdf_bytes,
            reference_json=reference_json,
            lxml=lxml,
            xyz_local=xyz_local,
            xyz_georef=xyz_georef,
            xyz_geo=xyz_geo,
            dxf_local=dxf_local,
            dxf_georef=dxf_georef,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"TerrainIQ export generation failed: {exc}") from exc

    safe = _safe_name(body.project_name, "terrainiq_exports")
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe}_terrainiq_exports.zip"'},
    )
