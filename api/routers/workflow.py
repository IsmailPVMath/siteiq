"""Unified workflow endpoints for the React app (Streamlit uses legacy modules)."""

from __future__ import annotations

import asyncio
import os
from functools import partial

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_user
from api.schemas.workflow import (
    WorkflowLayoutMatrixRequest,
    WorkflowLayoutMatrixResponse,
    WorkflowScoreRequest,
    WorkflowScoreResponse,
    WorkflowScreenRequest,
    WorkflowScreenResponse,
)
from pvmath_supabase import AuthUser, increment_usage, is_over_limit
from pvmath_workflow.layout_matrix import run_fixed_tilt_layout_matrix
from pvmath_workflow.scoring import unified_pvmath_score
from pvmath_workflow.screen import WorkflowScreenRequest as ScreenReq, run_workflow_screen

router = APIRouter(tags=["workflow"])

SCREEN_APP = "siteiq"
SCREEN_TIMEOUT_SEC = int(os.environ.get("PVMATH_GATE_TIMEOUT", "120"))
LAYOUT_TIMEOUT_SEC = int(os.environ.get("PVMATH_LAYOUT_TIMEOUT", "120"))


def _limit_detail() -> str:
    return (
        "Monthly analysis limit reached. Free plan: 5 SiteIQ analyses per month. "
        "Upgrade at contact@pvmath.com"
    )


@router.post("/workflow/screen", response_model=WorkflowScreenResponse)
async def workflow_screen(
    body: WorkflowScreenRequest,
    user: AuthUser = Depends(get_current_user),
):
    """
    Unified workflow step 1 — solar, flood, regulatory, capacity.

    No terrain slope here; TopoIQ is the only terrain source in the React workflow.
    """
    if user.access_token and is_over_limit(user.user_id, SCREEN_APP, user.access_token):
        raise HTTPException(status_code=429, detail=_limit_detail())

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
    """Combine screening partial scores with TopoIQ terrain_score for the final PVMath score."""
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
            "PVMath score combines screening (solar, flood, land, regulatory) with "
            f"TopoIQ terrain ({body.terrain_score}/100). Terrain caps the overall score "
            "on challenging sites — excellent solar cannot mask poor slope distribution."
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
