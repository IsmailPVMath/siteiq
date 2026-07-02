"""Gate analysis endpoints."""

from __future__ import annotations

import asyncio
import os
from functools import partial

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_user
from api.schemas.gate import GateAnalyzeRequest, GateAnalyzeResponse
from pvmath_gate.analyze import run_gate_analysis
from pvmath_gate.models import GateRequest
from pvmath_supabase import AuthUser, PLATFORM_APP, increment_usage, is_over_limit, usage_limit_detail

router = APIRouter(tags=["gate"])

GATE_APP = PLATFORM_APP
GATE_TIMEOUT_SEC = int(os.environ.get("PVMATH_GATE_TIMEOUT", "120"))


def _limit_detail(user: AuthUser) -> str:
    from pvmath_supabase import get_plan

    plan = get_plan(user.user_id, user.access_token) if user.access_token else "free"
    return usage_limit_detail(plan)


def _build_gate_request(body: GateAnalyzeRequest) -> GateRequest:
    boundary = None
    if body.boundary:
        boundary = [[p.lat, p.lon] for p in body.boundary]
        if len(boundary) < 3:
            raise HTTPException(
                status_code=422,
                detail="boundary requires at least 3 points",
            )

    return GateRequest(
        project_name=body.project_name,
        lat=body.lat,
        lon=body.lon,
        area_ha=body.area_ha,
        land_use=body.land_use,
        mount_type=body.mount_type,
        country=body.country,
        boundary=boundary,
        run_layout=body.run_layout,
        module_h=body.module_h,
        module_w=body.module_w,
        module_wp=body.module_wp,
        n_portrait=body.n_portrait,
        pitch_m=body.pitch_m,
        setback_m=body.setback_m,
        gcr_1p=body.gcr_1p,
        gcr_2p=body.gcr_2p,
    )


def _to_response(result) -> GateAnalyzeResponse:
    return GateAnalyzeResponse(
        success=result.success,
        project_name=result.project_name,
        coordinates=result.coordinates,
        solar=result.solar,
        terrain=result.terrain,
        flood=result.flood,
        regulatory=result.regulatory,
        capacity=result.capacity,
        yield_configs=result.yield_configs,
        layout=result.layout,
        bom=result.bom,
        pvmath_score=result.pvmath_score,
        verdict=result.verdict,
        verdict_detail=result.verdict_detail,
        errors=result.errors,
        api_version=result.api_version,
    )


@router.post("/gate/analyze", response_model=GateAnalyzeResponse)
async def analyze_gate(
    body: GateAnalyzeRequest,
    user: AuthUser = Depends(get_current_user),
):
    """
    Unified gate analysis — one call, full screening payload.

    Requires Supabase Bearer token.
    """
    req = _build_gate_request(body)
    loop = asyncio.get_running_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(None, partial(run_gate_analysis, req)),
            timeout=GATE_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=(
                f"Gate analysis timed out after {GATE_TIMEOUT_SEC}s. "
                "Try run_layout=false or a smaller area."
            ),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Gate analysis failed: {exc}",
        ) from exc

    return _to_response(result)
