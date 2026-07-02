"""Pydantic schemas for RevenueIQ (staging-only module)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RevenueIQAnalyzeRequest(BaseModel):
    project_name: str = Field(default="", max_length=200)
    country: str = Field(default="", max_length=120)
    land_use: str = Field(default="Standard")
    mount_type: str = Field(default="Fixed Tilt")
    dc_kwp: float = Field(..., gt=0, description="Layout DC capacity (kWp)")
    annual_mwh: float = Field(..., gt=0, description="Annual energy from YieldIQ (MWh)")
    site_area_ha: float = Field(default=0.0, ge=0)
    mean_slope_pct: Optional[float] = Field(default=None, ge=0)
    grid_distance_km: Optional[float] = Field(default=None, ge=0)
    terrain_grade: str = Field(
        default="good",
        description="Fallback terrain tier if mean_slope_pct missing",
    )
    wacc_pct: float = Field(default=6.5, ge=0, le=30)
    project_lifetime_yr: int = Field(default=25, ge=1, le=40)
    tariff_override_local_mwh: Optional[float] = Field(
        default=None,
        description="Tariff override in local currency per MWh",
    )
    capex_override_eur_kwp: Optional[float] = Field(default=None, ge=0)
    itc_rate: float = Field(default=0.0, ge=0, le=1)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)


class RevenueIQAnalyzeResponse(BaseModel):
    success: bool
    errors: List[str] = Field(default_factory=list)
    local_currency: str = "EUR"
    eur_fx_rate: float = 1.0
    capex_lo_eur: float = 0.0
    capex_hi_eur: float = 0.0
    capex_lo_local: float = 0.0
    capex_hi_local: float = 0.0
    itc_credit_eur: float = 0.0
    effective_capex_lo_eur: float = 0.0
    effective_capex_hi_eur: float = 0.0
    capex_breakdown: Dict[str, Any] = Field(default_factory=dict)
    opex_lo_eur_yr: float = 0.0
    opex_hi_eur_yr: float = 0.0
    opex_lo_local_yr: float = 0.0
    opex_hi_local_yr: float = 0.0
    tariff_mode: str = "PPA"
    tariff_label: str = ""
    tariff_lo_eur_mwh: float = 0.0
    tariff_hi_eur_mwh: float = 0.0
    tariff_lo_local_mwh: float = 0.0
    tariff_hi_local_mwh: float = 0.0
    revenue_yr1_lo_eur: float = 0.0
    revenue_yr1_hi_eur: float = 0.0
    revenue_25yr_lo_eur: float = 0.0
    revenue_25yr_hi_eur: float = 0.0
    lcoe_lo_eur_mwh: float = 0.0
    lcoe_hi_eur_mwh: float = 0.0
    payback_lo_yr: Optional[float] = None
    payback_hi_yr: Optional[float] = None
    irr_lo_pct: Optional[float] = None
    irr_hi_pct: Optional[float] = None
    npv_lo_eur: Optional[float] = None
    npv_hi_eur: Optional[float] = None
    sensitivity: Dict[str, float] = Field(default_factory=dict)
    viability: str = "MARGINAL"
    viability_note: str = ""
    economic_score: int = 50
    wacc_pct: float = 6.5
    screening_disclaimer: str = ""
