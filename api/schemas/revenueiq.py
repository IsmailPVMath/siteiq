"""Pydantic schemas for RevenueIQ (staging-only module)."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class RevenueIQAnalyzeRequest(BaseModel):
    project_name: str = Field(default="", max_length=200)
    country: str = Field(default="", max_length=120)
    land_use: str = Field(default="Standard")
    mount_type: str = Field(default="Fixed Tilt")
    dc_kwp: float = Field(..., gt=0, description="Layout DC capacity (kWp)")
    annual_mwh: float = Field(..., gt=0, description="Annual energy from YieldIQ (MWh)")
    terrain_grade: str = Field(
        default="good",
        description="Terrain tier: excellent, good, acceptable, challenging, critical",
    )
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)


class RevenueTariffOut(BaseModel):
    label: str
    notes: str = ""
    revenue_eur_mwh_lo: float
    revenue_eur_mwh_hi: float


class RevenueCapexOut(BaseModel):
    eur_per_wp_lo: float
    eur_per_wp_hi: float
    total_eur_lo: float
    total_eur_hi: float


class RevenueIQAnalyzeResponse(BaseModel):
    success: bool
    currency_display: str = "EUR"
    tariff: RevenueTariffOut
    annual_revenue_eur_lo: float
    annual_revenue_eur_hi: float
    capex: RevenueCapexOut
    opex_eur_yr_lo: float
    opex_eur_yr_hi: float
    payback_years_lo: Optional[float] = None
    payback_years_hi: Optional[float] = None
    lcoe_eur_mwh_lo: Optional[float] = None
    lcoe_eur_mwh_hi: Optional[float] = None
    screening_disclaimer: str
    errors: List[str] = Field(default_factory=list)
