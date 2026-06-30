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
    """Screening-grade revenue, CAPEX band, payback, and LCOE from LayoutIQ + YieldIQ."""
    _require_enabled()
    result = run_revenue_analysis(
        RevenueIQRequest(
            project_name=body.project_name,
            country=body.country,
            land_use=body.land_use,
            mount_type=body.mount_type,
            dc_kwp=body.dc_kwp,
            annual_mwh=body.annual_mwh,
            terrain_grade=body.terrain_grade,
            lat=body.lat,
            lon=body.lon,
        )
    )
    d = result.to_dict()
    return RevenueIQAnalyzeResponse(
        success=d["success"],
        currency_display=d["currency_display"],
        tariff=d["tariff"],
        annual_revenue_eur_lo=d["annual_revenue_eur_lo"],
        annual_revenue_eur_hi=d["annual_revenue_eur_hi"],
        capex=d["capex"],
        opex_eur_yr_lo=d["opex_eur_yr_lo"],
        opex_eur_yr_hi=d["opex_eur_yr_hi"],
        payback_years_lo=d["payback_years_lo"],
        payback_years_hi=d["payback_years_hi"],
        lcoe_eur_mwh_lo=d["lcoe_eur_mwh_lo"],
        lcoe_eur_mwh_hi=d["lcoe_eur_mwh_hi"],
        screening_disclaimer=d["screening_disclaimer"],
        errors=d["errors"],
    )
