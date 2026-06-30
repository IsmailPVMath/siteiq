"""Unified workflow endpoints for the React app (Streamlit uses legacy modules)."""

from __future__ import annotations

import asyncio
import io
import os
from functools import partial

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from api.deps import get_current_user
from api.job_store import get_heavy_job, submit_heavy_job
from api.schemas.gis import WorkflowGisAnalysisRequest, WorkflowGisAnalysisResponse
from api.schemas.jobs import JobStartResponse, JobStatusResponse
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
from pvmath_workflow.buildable_engine import compute_layout_exclusion_rings
from pvmath_workflow.gis_analysis import GisAnalysisRequest, run_gis_analysis
from pvmath_workflow.imported_layout import build_imported_layout_detail
from pvmath_workflow.layout_detail import build_layout_detail, export_layout_dxf
from pvmath_workflow.layout_matrix import run_fixed_tilt_layout_matrix
from pvmath_workflow.layout_sweep import run_layout_sweep
from pvmath_workflow.project_report import build_pvmath_report_pdf, build_project_package_zip
from pvmath_workflow.scoring import unified_pvmath_score
from pvmath_workflow.screen import WorkflowScreenRequest as ScreenReq, run_workflow_screen
from pvmath_workflow.slope_restrictions import build_slope_restriction_polygons
from pvmath_workflow.terrain_bundle import build_terrain_files
from pvmath_workflow.terrain_mesh import build_terrain_mesh

router = APIRouter(tags=["workflow"])

SCREEN_APP = PLATFORM_APP
SCREEN_TIMEOUT_SEC = int(os.environ.get("PVMATH_GATE_TIMEOUT", "150"))
LAYOUT_TIMEOUT_SEC = int(os.environ.get("PVMATH_LAYOUT_TIMEOUT", "240"))
TOPO_TIMEOUT_SEC = int(os.environ.get("PVMATH_TOPO_TIMEOUT", "180"))
_MAX_DXF_BYTES = 16 * 1024 * 1024


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


def _render_slope_png(polys, topo) -> bytes | None:
    """Render the TerrainIQ slope-map PNG from boundary rings, mirroring the
    standalone /terrainiq report path so the unified report shows the same map.

    Returns PNG bytes or None when boundaries are absent / rendering fails.
    """
    if not polys:
        return None
    try:
        from pvmath_terrain_report import render_slope_map_png
        from pvmath_topo_engine import run_topo_analysis

        lonlat = [[(float(p[1]), float(p[0])) for p in ring] for ring in polys if len(ring) >= 3]
        if not lonlat:
            return None
        grid_m = 0.0
        try:
            grid_m = float((topo or {}).get("grid_m_used") or 0)
        except (TypeError, ValueError):
            grid_m = 0.0
        analysis = run_topo_analysis(lonlat, grid_m=grid_m or 10.0, allow_coarsen=True)
        bbox = analysis["bbox"]
        meta = analysis.get("terrain_source") or {}
        buf = render_slope_map_png(
            analysis["X"], analysis["Y"], analysis["Z"],
            float(analysis["grid_m_used"]),
            float(bbox["south"]), float(bbox["north"]),
            float(bbox["west"]), float(bbox["east"]),
            polygon_list=analysis["polygons"],
            terrain_source_used=str(analysis.get("terrain_source_used", "")),
            terrain_disclaimer=str(meta.get("disclaimer", "")),
            tiles=analysis.get("tiles"),
            zoom_to_extent=True,
            basemap=False,
        )
        return buf.getvalue() if buf else None
    except Exception:
        return None


def _rings_latlon_to_geojson(rings: list) -> dict | None:
    features = []
    for ring in rings or []:
        if not ring or len(ring) < 3:
            continue
        coords = [[float(p[1]), float(p[0])] for p in ring]
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        features.append(
            {
                "type": "Feature",
                "properties": {"category": "manual"},
                "geometry": {"type": "Polygon", "coordinates": [coords]},
            }
        )
    if not features:
        return None
    return {"type": "FeatureCollection", "features": features}


def _resolve_layout_restrictions(body, polys: list) -> list:
    """
    Build layout no-build rings.

    Default: use restriction_polygons from the client (full SiteIQ excluded union).
    EPC clearing mode: recompute hard GIS exclusions only (skip forests/vegetation)
    and merge manual project restriction zones.
    """
    manual = _latlon_polys(None, body.restriction_polygons)
    if getattr(body, "ignore_soft_constraints", False) and getattr(body, "constraint_layers", None):
        return compute_layout_exclusion_rings(
            polys,
            body.constraint_layers,
            setbacks_m=getattr(body, "setbacks_m", None),
            manual_restrictions_geojson=_rings_latlon_to_geojson(manual),
            ignore_soft_constraints=True,
        )
    if manual:
        return manual
    return _latlon_polys(None, body.restriction_polygons)


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


def _build_terrain_mesh_response(body: WorkflowTerrainMeshRequest) -> WorkflowTerrainMeshResponse:
    polygons = _lonlat_polys(body.boundary, body.boundaries)
    if not polygons:
        raise ValueError("A site boundary is required for terrain mesh.")
    data = build_terrain_mesh(
        polygons,
        grid_m=body.grid_m,
        max_vertices=body.max_vertices,
        mask_geojson=body.mask_geojson,
    )
    return WorkflowTerrainMeshResponse(**data)


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
            f"Combines SiteIQ screening with TerrainIQ terrain ({body.terrain_score}/100) "
            "and YieldIQ energy yield when run. Terrain caps the score — excellent solar "
            "cannot offset poor slopes. DC capacity comes from LayoutIQ, not screening."
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
    manual_restrictions = _resolve_layout_restrictions(body, polys)
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
                    prune_isolated_blocks=body.prune_isolated_blocks,
                    restriction_geojson=getattr(body, "restriction_geojson", None),
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
    manual_restrictions = _resolve_layout_restrictions(body, polys)
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
        prune_isolated_blocks=body.prune_isolated_blocks,
        restriction_geojson=getattr(body, "restriction_geojson", None),
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


@router.post("/workflow/layout-import-dxf", response_model=WorkflowLayoutDetailResponse)
async def workflow_layout_import_dxf(
    file: UploadFile = File(...),
    ref_lat: float = Form(...),
    ref_lon: float = Form(...),
    config_key: str = Form(default="SAT_2P"),
    pitch_m: float = Form(default=6.5),
    module_wp: int = Form(default=550),
    modules_per_string: int = Form(default=28),
    tracker_string_options: str = Form(default="8,7,6,5,4,3"),
    project_name: str = Form(default="Imported layout"),
    _user: AuthUser = Depends(get_current_user),
):
    """
    Import an external layout DXF (metric local coordinates).

    Strings on PV_MODULE layers are grouped into coloured 8S–1S tracker unit
    rectangles. Layers PV_8S … PV_1S are read directly. Reference lat/lon anchors
    the local DXF origin to the project site for map overlay and YieldIQ.
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty DXF file")
    if len(raw) > _MAX_DXF_BYTES:
        raise HTTPException(status_code=413, detail="DXF file too large (max 16 MB)")

    options = []
    for part in tracker_string_options.replace(" ", "").split(","):
        if part.isdigit() and int(part) > 0:
            options.append(int(part))
    if not options:
        options = [8, 7, 6, 5, 4, 3]

    loop = asyncio.get_running_loop()
    try:
        data = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                partial(
                    build_imported_layout_detail,
                    raw,
                    config_key=config_key,
                    pitch_m=pitch_m,
                    ref_lat=ref_lat,
                    ref_lon=ref_lon,
                    module_wp=module_wp,
                    modules_per_string=modules_per_string,
                    tracker_string_options=options,
                    project_name=project_name,
                ),
            ),
            timeout=LAYOUT_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"DXF import timed out after {LAYOUT_TIMEOUT_SEC}s.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DXF import failed: {exc}") from exc

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
    loop = asyncio.get_running_loop()
    try:
        data = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                partial(_build_terrain_mesh_response, body),
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
    return data


@router.post("/workflow/terrain-mesh-job", response_model=JobStartResponse)
async def start_workflow_terrain_mesh_job(
    body: WorkflowTerrainMeshRequest,
    user: AuthUser = Depends(get_current_user),
):
    """Start terrain mesh generation as a background job for large sites."""
    try:
        job = submit_heavy_job(
            user.user_id,
            "workflow.terrain_mesh",
            partial(_build_terrain_mesh_response, body),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return JobStartResponse(job_id=job.id, kind=job.kind, status=job.status)


@router.get("/workflow/terrain-mesh-job/{job_id}", response_model=JobStatusResponse)
async def get_workflow_terrain_mesh_job(
    job_id: str,
    user: AuthUser = Depends(get_current_user),
):
    job = get_heavy_job(user.user_id, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(**job.public())


@router.post("/workflow/pvmath-report-pdf")
async def workflow_pvmath_report_pdf(
    body: WorkflowPvmathReportRequest,
    _user: AuthUser = Depends(get_current_user),
):
    """Unified A4 PDF: SiteIQ → TerrainIQ → YieldIQ with charts and verdict cards."""
    polys = _latlon_polys(body.boundary, body.boundaries)
    slope_png = _render_slope_png(polys, body.topo)
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
                    mount_type=body.mount_type,
                    area_ha=body.area_ha,
                    location_label=body.location_label,
                    screening=body.screening,
                    topo=body.topo,
                    score=body.score,
                    layout_row=body.layout_row,
                    yield_result=body.yield_result,
                    selected_yield_mwh=body.selected_yield_mwh,
                    selected_config_key=body.selected_config_key,
                    selected_dc_kwp=body.selected_dc_kwp,
                    boundaries=polys,
                    slope_img_png=slope_png,
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
    """ZIP deliverables: PVMath report PDF, A1 layout+BOM PDF, BOM CSV, layout DXF."""
    polys = _latlon_polys(body.boundary, body.boundaries)
    if not polys:
        raise HTTPException(status_code=400, detail="A site boundary is required for the project package.")
    loop = asyncio.get_running_loop()
    try:
        manual_restrictions = await asyncio.wait_for(
            loop.run_in_executor(None, partial(_resolve_layout_restrictions, body, polys)),
            timeout=LAYOUT_TIMEOUT_SEC,
        )
        tracker_restrictions = await asyncio.wait_for(
            loop.run_in_executor(None, partial(_tracker_slope_restrictions, body)),
            timeout=LAYOUT_TIMEOUT_SEC,
        )
        restrictions = manual_restrictions
        if (body.config_key or "").upper().startswith("SAT"):
            restrictions = _merge_latlon_polys(manual_restrictions, tracker_restrictions)
        terrain_files = None
        if body.include_terrain:
            terrain_polys = _lonlat_polys(body.boundary, body.boundaries)
            if terrain_polys:
                try:
                    terrain_files = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            partial(
                                build_terrain_files,
                                terrain_polys,
                                project_name=body.project_name,
                                country=body.country,
                                land_use=body.land_use,
                                grid_m=body.topo_grid_m,
                                allow_coarsen=body.topo_allow_coarsen,
                                contour_minor=body.contour_minor,
                                contour_major=body.contour_major,
                                mask_geojson=body.mask_geojson,
                            ),
                        ),
                        timeout=TOPO_TIMEOUT_SEC,
                    )
                except Exception:
                    # Terrain data is a best-effort add-on; never fail the whole
                    # package if the DEM fetch / analysis times out or errors.
                    terrain_files = None
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
                    mount_type=body.mount_type,
                    area_ha=body.area_ha,
                    boundaries=polys,
                    restriction_polygons=restrictions,
                    restriction_geojson=getattr(body, "restriction_geojson", None),
                    constraint_layers=getattr(body, "constraint_layers", None),
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
                    prune_isolated_blocks=body.prune_isolated_blocks,
                    screening=body.screening,
                    topo=body.topo,
                    score=body.score,
                    layout_row=body.layout_row,
                    yield_result=body.yield_result,
                    selected_yield_mwh=body.selected_yield_mwh,
                    location_label=body.location_label,
                    drawn_by=body.drawn_by,
                    revision=body.revision,
                    terrain_files=terrain_files,
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
