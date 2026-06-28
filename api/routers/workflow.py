"""Unified workflow endpoints for the React app (Streamlit uses legacy modules)."""

from __future__ import annotations

import asyncio
import io
import os
from functools import partial

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from api.deps import get_current_user
from api.schemas.gis import WorkflowGisAnalysisRequest, WorkflowGisAnalysisResponse
from api.schemas.workflow import (
    WorkflowLayoutDetailRequest,
    WorkflowLayoutDetailResponse,
    WorkflowLayoutMatrixRequest,
    WorkflowLayoutMatrixResponse,
    WorkflowLayoutSweepRequest,
    WorkflowLayoutSweepResponse,
    WorkflowPvmathReportRequest,
    WorkflowProjectPackageRequest,
    WorkflowScoreRequest,
    WorkflowScoreResponse,
    WorkflowScreenRequest,
    WorkflowScreenResponse,
    WorkflowTerrainMeshRequest,
    WorkflowTerrainMeshResponse,
)
from pvmath_supabase import (
    AuthUser,
    PLATFORM_APP,
    increment_usage,
    is_over_limit,
    usage_limit_detail,
)
from pvmath_workflow.gis_analysis import GisAnalysisRequest, run_gis_analysis
from pvmath_workflow.layout_detail import build_layout_detail, export_layout_dxf
from pvmath_workflow.layout_matrix import run_fixed_tilt_layout_matrix
from pvmath_workflow.layout_sweep import run_layout_sweep
from pvmath_workflow.project_report import build_pvmath_report_pdf, build_project_package_zip
from pvmath_workflow.scoring import unified_pvmath_score
from pvmath_workflow.screen import WorkflowScreenRequest as ScreenReq, run_workflow_screen
from pvmath_workflow.slope_restrictions import build_slope_restriction_polygons
from pvmath_workflow.terrain_mesh import build_terrain_mesh

router = APIRouter(tags=["workflow"])

SCREEN_APP = PLATFORM_APP
SCREEN_TIMEOUT_SEC = int(os.environ.get("PVMATH_GATE_TIMEOUT", "150"))
LAYOUT_TIMEOUT_SEC = int(os.environ.get("PVMATH_LAYOUT_TIMEOUT", "240"))


def _latlon_polys(boundary, boundaries):
    """Normalize request points into a list of [lat, lon] rings."""
    polys = []
    for ring in boundaries or []:
        pts = [[p.lat, p.lon] for p in ring]
        if len(pts) >= 3:
            polys.append(pts)
    if not polys and boundary:
        pts = [[p.lat, p.lon] for p in boundary]
        if len(pts) >= 3:
            polys.append(pts)
    return polys


def _merge_latlon_polys(*groups):
    merged = []
    for group in groups:
        for ring in group or []:
            if ring and len(ring) >= 3:
                merged.append(ring)
    return merged


def _tracker_slope_restrictions(body) -> list:
    if not getattr(body, "exclude_tracker_slope", False):
        return []
    polygons = _lonlat_polys(body.boundary, body.boundaries)
    if not polygons:
        return []
    data = build_slope_restriction_polygons(
        polygons,
        slope_limit_pct=body.tracker_slope_limit_pct,
        grid_m=body.slope_restriction_grid_m,
    )
    return data.get("restriction_polygons") or []


def _lonlat_polys(boundary, boundaries):
    """Normalize request points into a list of (lon, lat) rings for TerrainIQ."""
    polys = []
    for ring in boundaries or []:
        pts = [(p.lon, p.lat) for p in ring]
        if len(pts) >= 3:
            polys.append(pts)
    if not polys and boundary:
        pts = [(p.lon, p.lat) for p in boundary]
        if len(pts) >= 3:
            polys.append(pts)
    return polys


def _limit_detail(user: AuthUser) -> str:
    from pvmath_supabase import get_plan

    plan = get_plan(user.user_id, user.access_token) if user.access_token else "free"
    return usage_limit_detail(plan)


GIS_TIMEOUT_SEC = int(os.environ.get("PVMATH_GIS_TIMEOUT", "180"))


@router.post("/workflow/gis-analysis", response_model=WorkflowGisAnalysisResponse)
async def workflow_gis_analysis(
    body: WorkflowGisAnalysisRequest,
    user: AuthUser = Depends(get_current_user),
):
    """
    SiteIQ intelligent GIS — detect OSM constraints, apply setbacks, compute buildable area.

  Automatically queries roads, railways, buildings, water, forests, and transmission
  lines inside the site boundary. No user input required beyond the boundary polygon.
    """
    if user.access_token and is_over_limit(user.user_id, SCREEN_APP, user.access_token):
        raise HTTPException(status_code=429, detail=_limit_detail(user))

    rings = []
    for ring in body.boundaries or []:
        rings.append([(p.lat, p.lon) for p in ring])
    boundary_pts = [(p.lat, p.lon) for p in body.boundary] if body.boundary else []

    req = GisAnalysisRequest(
        boundary=boundary_pts,
        boundaries=rings,
        restriction_polygons_geojson=body.restriction_polygons_geojson,
        setbacks_m=body.setbacks_m,
        constraint_layers=body.constraint_layers,
        include_grid=body.include_grid,
    )
    loop = asyncio.get_running_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(None, partial(run_gis_analysis, req)),
            timeout=GIS_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"GIS analysis timed out after {GIS_TIMEOUT_SEC}s.",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"GIS analysis failed: {exc}") from exc

    if not result.get("success"):
        return WorkflowGisAnalysisResponse(success=False, error=result.get("error", "GIS failed"))

    return WorkflowGisAnalysisResponse(**result)


@router.post("/workflow/screen", response_model=WorkflowScreenResponse)
async def workflow_screen(
    body: WorkflowScreenRequest,
    user: AuthUser = Depends(get_current_user),
):
    """
    Unified workflow step 1 — solar, flood, regulatory, capacity.

    No terrain slope here; TerrainIQ is the only terrain source in the React workflow.
    """
    if user.access_token and is_over_limit(user.user_id, SCREEN_APP, user.access_token):
        raise HTTPException(status_code=429, detail=_limit_detail(user))

    req = ScreenReq(
        project_name=body.project_name,
        lat=body.lat,
        lon=body.lon,
        area_ha=body.area_ha,
        land_use=body.land_use,
        mount_type=body.mount_type,
        country=body.country,
    )
    loop = asyncio.get_running_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(None, partial(run_workflow_screen, req)),
            timeout=SCREEN_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Screening timed out after {SCREEN_TIMEOUT_SEC}s.",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Screening failed: {exc}") from exc

    if user.access_token:
        increment_usage(user.user_id, SCREEN_APP, user.access_token)

    return WorkflowScreenResponse(
        success=result.success,
        project_name=result.project_name,
        coordinates=result.coordinates,
        solar=result.solar,
        flood=result.flood,
        grid=result.grid,
        regulatory=result.regulatory,
        capacity=result.capacity,
        score_components=result.score_components,
        terrain_note=result.terrain_note,
        errors=result.errors,
    )


@router.post("/workflow/score", response_model=WorkflowScoreResponse)
async def workflow_score(
    body: WorkflowScoreRequest,
    _user: AuthUser = Depends(get_current_user),
):
    """Combine screening partial scores with TerrainIQ terrain_score for the final PVMath score."""
    comps = body.score_components
    scored = unified_pvmath_score(
        solar_score=int(comps.get("solar", 55)),
        terrain_score=int(body.terrain_score),
        flood_score=int(comps.get("flood", 55)),
        land_score=int(comps.get("land", 72)),
        regulatory_score=int(comps.get("regulatory", 75)),
    )
    return WorkflowScoreResponse(
        pvmath_score=scored["pvmath_score"],
        verdict=scored["verdict"],
        components=scored["components"],
        verdict_detail=(
            "PVMath score blends the SiteIQ screening ratings (solar, flood, land, regulatory) "
            f"with the authoritative TerrainIQ terrain score ({body.terrain_score}/100). Terrain "
            "caps the overall score on challenging sites — strong solar cannot mask poor slope "
            "distribution. Capacity and yield are reported separately in LayoutIQ and YieldIQ."
        ),
    )


@router.post("/workflow/layout-matrix", response_model=WorkflowLayoutMatrixResponse)
async def workflow_layout_matrix(
    body: WorkflowLayoutMatrixRequest,
    user: AuthUser = Depends(get_current_user),
):
    """Fixed Tilt 1P–4P portrait layout + BOM matrix on the site boundary."""
    boundary = [[p.lat, p.lon] for p in body.boundary]
    loop = asyncio.get_running_loop()
    try:
        configs = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                partial(
                    run_fixed_tilt_layout_matrix,
                    boundary,
                    module_h=body.module_h,
                    module_w=body.module_w,
                    module_wp=body.module_wp,
                    pitch_m=body.pitch_m,
                    setback_m=body.setback_m,
                    azimuth=body.azimuth,
                    modules_per_string=body.modules_per_string,
                    strings_per_inv=body.strings_per_inv,
                    inv_ac_kw=body.inv_ac_kw,
                ),
            ),
            timeout=LAYOUT_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Layout matrix timed out after {LAYOUT_TIMEOUT_SEC}s.",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Layout matrix failed: {exc}") from exc

    return WorkflowLayoutMatrixResponse(configs=configs)


@router.post("/workflow/layout-sweep", response_model=WorkflowLayoutSweepResponse)
async def workflow_layout_sweep(
    body: WorkflowLayoutSweepRequest,
    user: AuthUser = Depends(get_current_user),
):
    """
    LayoutIQ sweep — Fixed Tilt 1P–4P and Tracker 1P–2P across increasing pitch/GCR.

    Returns a comparison table (capacity vs pitch) plus best DC per configuration.
    """
    polys = _latlon_polys(body.boundary, body.boundaries)
    if not polys:
        raise HTTPException(status_code=400, detail="A site boundary is required for LayoutIQ.")
    manual_restrictions = _latlon_polys(None, body.restriction_polygons)
    loop = asyncio.get_running_loop()
    try:
        tracker_restrictions = await asyncio.wait_for(
            loop.run_in_executor(None, partial(_tracker_slope_restrictions, body)),
            timeout=LAYOUT_TIMEOUT_SEC,
        )
        data = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                partial(
                    run_layout_sweep,
                    boundaries=polys,
                    restriction_polygons=manual_restrictions,
                    tracker_restriction_polygons=tracker_restrictions,
                    module_h=body.module_h,
                    module_w=body.module_w,
                    module_wp=body.module_wp,
                    setback_m=body.setback_m,
                    azimuth=body.azimuth,
                    pitch_steps_m=body.pitch_steps_m,
                    optimization_mode=body.optimization_mode,
                    land_cost=body.land_cost,
                    country=body.country,
                    lat=body.lat,
                    bifacial=body.bifacial,
                    custom_gcr=body.custom_gcr,
                    custom_pitch_m=body.custom_pitch_m,
                    include_bom=body.include_bom,
                    modules_per_string=body.modules_per_string,
                    inter_string_gap_m=body.inter_string_gap_m,
                    tracker_string_options=body.tracker_string_options,
                    max_tracker_length_m=body.max_tracker_length_m,
                    rows_per_block=body.rows_per_block,
                    block_gap_m=body.block_gap_m,
                    ns_gap_1_m=body.ns_gap_1_m,
                    cols_per_block=body.cols_per_block,
                    ew_gap_m=body.ew_gap_m,
                    road_mode=body.road_mode,
                    road_preset=body.road_preset,
                    mount_filter=body.mount_filter,
                    portrait_filter=body.portrait_filter,
                    row_alignment=body.row_alignment,
                    allow_partial_strings=body.allow_partial_strings,
                ),
            ),
            timeout=LAYOUT_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Layout sweep timed out after {LAYOUT_TIMEOUT_SEC}s.",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Layout sweep failed: {exc}") from exc

    return WorkflowLayoutSweepResponse(
        rows=data.get("rows") or [],
        best_by_config=data.get("best_by_config") or {},
        recommended_by_config=data.get("recommended_by_config") or {},
        gcr_guidance=data.get("gcr_guidance") or {},
        strategy=data.get("strategy") or {},
        layout_params=data.get("layout_params") or {},
        config_count=int(data.get("config_count") or 0),
        row_count=int(data.get("row_count") or 0),
    )


def _layout_detail_payload(body: WorkflowLayoutDetailRequest):
    polys = _latlon_polys(body.boundary, body.boundaries)
    if not polys:
        raise ValueError("A site boundary is required")
    manual_restrictions = _latlon_polys(None, body.restriction_polygons)
    tracker_restrictions = _tracker_slope_restrictions(body)
    restrictions = manual_restrictions
    if (body.config_key or "").upper().startswith("SAT"):
        restrictions = _merge_latlon_polys(manual_restrictions, tracker_restrictions)
    return partial(
        build_layout_detail,
        boundaries=polys,
        restriction_polygons=restrictions,
        config_key=body.config_key,
        pitch_m=body.pitch_m,
        module_h=body.module_h,
        module_w=body.module_w,
        module_wp=body.module_wp,
        setback_m=body.setback_m,
        azimuth=body.azimuth,
        modules_per_string=body.modules_per_string,
        inter_string_gap_m=body.inter_string_gap_m,
        tracker_string_options=body.tracker_string_options,
        max_tracker_length_m=body.max_tracker_length_m,
        rows_per_block=body.rows_per_block,
        block_gap_m=body.block_gap_m,
        ns_gap_1_m=body.ns_gap_1_m,
        cols_per_block=body.cols_per_block,
        ew_gap_m=body.ew_gap_m,
        road_mode=body.road_mode,
        road_preset=body.road_preset,
        allow_partial_strings=body.allow_partial_strings,
        row_alignment=body.row_alignment,
    )


@router.post("/workflow/layout-detail", response_model=WorkflowLayoutDetailResponse)
async def workflow_layout_detail(
    body: WorkflowLayoutDetailRequest,
    _user: AuthUser = Depends(get_current_user),
):
    """Detailed LayoutIQ row geometry for the browser map overlay."""
    loop = asyncio.get_running_loop()
    try:
        data = await asyncio.wait_for(
            loop.run_in_executor(None, _layout_detail_payload(body)),
            timeout=LAYOUT_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Layout detail timed out after {LAYOUT_TIMEOUT_SEC}s.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Layout detail failed: {exc}") from exc

    data.pop("layout", None)
    data.pop("layouts", None)
    return WorkflowLayoutDetailResponse(**data)


@router.post("/workflow/layout-dxf")
async def workflow_layout_dxf(
    body: WorkflowLayoutDetailRequest,
    _user: AuthUser = Depends(get_current_user),
):
    """Download selected LayoutIQ row geometry as a metric local-coordinate DXF."""
    loop = asyncio.get_running_loop()
    try:
        detail = await asyncio.wait_for(
            loop.run_in_executor(None, _layout_detail_payload(body)),
            timeout=LAYOUT_TIMEOUT_SEC,
        )
        dxf_bytes = await asyncio.wait_for(
            loop.run_in_executor(None, partial(export_layout_dxf, detail, body.project_name)),
            timeout=LAYOUT_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Layout DXF timed out after {LAYOUT_TIMEOUT_SEC}s.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Layout DXF failed: {exc}") from exc

    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in body.project_name)[:60]
    filename = f"{safe_name or 'LayoutIQ'}_{body.config_key}_{body.pitch_m:g}m.dxf"
    return StreamingResponse(
        io.BytesIO(dxf_bytes),
        media_type="application/dxf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/workflow/terrain-mesh", response_model=WorkflowTerrainMeshResponse)
async def workflow_terrain_mesh(
    body: WorkflowTerrainMeshRequest,
    _user: AuthUser = Depends(get_current_user),
):
    """Coarse TerrainIQ terrain mesh for browser-side 3D rendering."""
    polygons = _lonlat_polys(body.boundary, body.boundaries)
    if not polygons:
        raise HTTPException(status_code=400, detail="A site boundary is required for terrain mesh.")
    loop = asyncio.get_running_loop()
    try:
        data = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                partial(
                    build_terrain_mesh,
                    polygons,
                    grid_m=body.grid_m,
                    max_vertices=body.max_vertices,
                    mask_geojson=body.mask_geojson,
                ),
            ),
            timeout=LAYOUT_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Terrain mesh timed out after {LAYOUT_TIMEOUT_SEC}s.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Terrain mesh failed: {exc}") from exc
    return WorkflowTerrainMeshResponse(**data)


@router.post("/workflow/pvmath-report-pdf")
async def workflow_pvmath_report_pdf(
    body: WorkflowPvmathReportRequest,
    _user: AuthUser = Depends(get_current_user),
):
    """Unified A4 PDF: SiteIQ screening → TerrainIQ → LayoutIQ → YieldIQ → overall score."""
    loop = asyncio.get_running_loop()
    try:
        pdf_bytes = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                partial(
                    build_pvmath_report_pdf,
                    project_name=body.project_name,
                    country=body.country,
                    lat=body.lat,
                    lon=body.lon,
                    land_use=body.land_use,
                    screening=body.screening,
                    topo=body.topo,
                    score=body.score,
                    layout_row=body.layout_row,
                    yield_result=body.yield_result,
                    selected_yield_mwh=body.selected_yield_mwh,
                ),
            ),
            timeout=LAYOUT_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="PVMath report timed out.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PVMath report failed: {exc}") from exc

    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in body.project_name)[:60]
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe or "PVMath"}_Report.pdf"'},
    )


@router.post("/workflow/project-package")
async def workflow_project_package(
    body: WorkflowProjectPackageRequest,
    _user: AuthUser = Depends(get_current_user),
):
    """ZIP deliverables: PVMath report PDF, A3 layout+BOM PDF, BOM CSV, layout DXF."""
    polys = _latlon_polys(body.boundary, body.boundaries)
    if not polys:
        raise HTTPException(status_code=400, detail="A site boundary is required for the project package.")
    manual_restrictions = _latlon_polys(None, body.restriction_polygons)
    loop = asyncio.get_running_loop()
    try:
        tracker_restrictions = await asyncio.wait_for(
            loop.run_in_executor(None, partial(_tracker_slope_restrictions, body)),
            timeout=LAYOUT_TIMEOUT_SEC,
        )
        restrictions = manual_restrictions
        if (body.config_key or "").upper().startswith("SAT"):
            restrictions = _merge_latlon_polys(manual_restrictions, tracker_restrictions)
        zip_bytes = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                partial(
                    build_project_package_zip,
                    project_name=body.project_name,
                    country=body.country,
                    lat=body.lat,
                    lon=body.lon,
                    land_use=body.land_use,
                    boundaries=polys,
                    restriction_polygons=restrictions,
                    config_key=body.config_key,
                    pitch_m=body.pitch_m,
                    module_h=body.module_h,
                    module_w=body.module_w,
                    module_wp=body.module_wp,
                    setback_m=body.setback_m,
                    azimuth=body.azimuth,
                    modules_per_string=body.modules_per_string,
                    inter_string_gap_m=body.inter_string_gap_m,
                    tracker_string_options=body.tracker_string_options,
                    max_tracker_length_m=body.max_tracker_length_m,
                    rows_per_block=body.rows_per_block,
                    block_gap_m=body.block_gap_m,
                    ns_gap_1_m=body.ns_gap_1_m,
                    cols_per_block=body.cols_per_block,
                    ew_gap_m=body.ew_gap_m,
                    road_mode=body.road_mode,
                    road_preset=body.road_preset,
                    screening=body.screening,
                    topo=body.topo,
                    score=body.score,
                    layout_row=body.layout_row,
                    yield_result=body.yield_result,
                    selected_yield_mwh=body.selected_yield_mwh,
                ),
            ),
            timeout=LAYOUT_TIMEOUT_SEC * 2,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Project package timed out.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Project package failed: {exc}") from exc

    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in body.project_name)[:60]
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe or "PVMath"}_Project_Package.zip"'},
    )
