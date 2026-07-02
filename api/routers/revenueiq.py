"""RevenueIQ endpoint — enabled only when PVMATH_ENABLE_REVENUEIQ=1 (staging)."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_user
from api.schemas.revenueiq import RevenueIQAnalyzeRequest, RevenueIQAnalyzeResponse
from pvmath_supabase import AuthUser
from revenueiq.engine import RevenueIQRequest, run_revenue_analysis

router = APIRouter(tags=["revenueiq"])

_ENABLED = os.environ.get("PVMATH_ENABLE_REVENUEIQ", "").strip().lower() in ("1", "true", "yes")


def _require_enabled() -> None:
    if not _ENABLED:
        raise HTTPException(
            status_code=404,
            detail="RevenueIQ is not enabled on this environment.",
        )


@router.post("/revenueiq/analyze", response_model=RevenueIQAnalyzeResponse)
async def analyze_revenueiq(
    body: RevenueIQAnalyzeRequest,
    _user: AuthUser = Depends(get_current_user),
):
    """Screening-grade revenue, CAPEX, OPEX, IRR, NPV, and LCOE from LayoutIQ + YieldIQ."""
    _require_enabled()
    result = run_revenue_analysis(
        RevenueIQRequest(
            project_name=body.project_name,
            country=body.country,
            land_use=body.land_use,
            mount_type=body.mount_type,
            dc_kwp=body.dc_kwp,
            annual_mwh=body.annual_mwh,
            site_area_ha=body.site_area_ha,
            mean_slope_pct=body.mean_slope_pct,
            grid_distance_km=body.grid_distance_km,
            terrain_grade=body.terrain_grade,
            wacc_pct=body.wacc_pct,
            project_lifetime_yr=body.project_lifetime_yr,
            tariff_override_local_mwh=body.tariff_override_local_mwh,
            capex_override_eur_kwp=body.capex_override_eur_kwp,
            itc_rate=body.itc_rate,
            lat=body.lat,
            lon=body.lon,
        )
    )
    return RevenueIQAnalyzeResponse(**result.to_dict())
