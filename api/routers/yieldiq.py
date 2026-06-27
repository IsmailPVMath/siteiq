"""YieldIQ analysis endpoint."""

from __future__ import annotations

import asyncio
import os
from functools import partial
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_user
from api.schemas.yieldiq import YieldIQAnalyzeRequest, YieldIQAnalyzeResponse
from pvmath_supabase import AuthUser, PLATFORM_APP, is_over_limit, usage_limit_detail
from pvmath_yield import (
    PROFILE_ANALYSIS,
    config_display_name,
    fetch_solar_resource,
    fetch_yield_cross_ref_bundle,
    profile_description,
    run_all_configs,
)

router = APIRouter(tags=["yieldiq"])

YIELD_APP = PLATFORM_APP
YIELD_TIMEOUT_SEC = int(os.environ.get("PVMATH_YIELD_TIMEOUT", "120"))


def _limit_detail(user: AuthUser) -> str:
    from pvmath_supabase import get_plan

    plan = get_plan(user.user_id, user.access_token) if user.access_token else "free"
    return usage_limit_detail(plan)


def _run_yield(body: YieldIQAnalyzeRequest) -> Dict[str, Any]:
    results, raddatabase = run_all_configs(
        body.lat,
        body.lon,
        body.gcr_1p,
        body.gcr_2p,
        body.soiling_loss,
        body.other_loss,
    )
    cross_ref = fetch_yield_cross_ref_bundle(body.lat, body.lon)
    solar_resource = fetch_solar_resource(body.lat, body.lon, raddatabase)
    configs: Dict[str, Dict[str, Any]] = {}
    for key, payload in results.items():
        item = dict(payload)
        item["display_name"] = config_display_name(key)
        configs[key] = item
    return {
        "raddatabase": raddatabase,
        "configs": configs,
        "cross_ref": cross_ref,
        "solar_resource": solar_resource,
    }


@router.post("/yieldiq/analyze", response_model=YieldIQAnalyzeResponse)
async def analyze_yieldiq(
    body: YieldIQAnalyzeRequest,
    user: AuthUser = Depends(get_current_user),
):
    if user.access_token and is_over_limit(user.user_id, YIELD_APP, user.access_token):
        raise HTTPException(status_code=429, detail=_limit_detail(user))

    loop = asyncio.get_running_loop()
    try:
        data = await asyncio.wait_for(
            loop.run_in_executor(None, partial(_run_yield, body)),
            timeout=YIELD_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"YieldIQ analysis timed out after {YIELD_TIMEOUT_SEC}s.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"YieldIQ analysis failed: {exc}",
        ) from exc

    disclosure = (
        f"{profile_description(PROFILE_ANALYSIS)}. "
        "Early screening — not bankable yield. Verify with detailed modelling (PVsyst, DNV, etc.) before financial close."
    )
    return YieldIQAnalyzeResponse(
        lat=body.lat,
        lon=body.lon,
        mount_type=body.mount_type,
        raddatabase=data["raddatabase"],
        configs=data["configs"],
        cross_ref_bundle=data["cross_ref"],
        solar_resource=data["solar_resource"],
        disclosure=disclosure,
    )
