"""RevenueIQ screening engine — revenue, CAPEX band, payback, LCOE snapshot."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from revenueiq.capex import capex_band_eur_wp, total_capex_eur
from revenueiq.tariffs import resolve_tariff, tariff_eur_mwh

# OPEX as % of CAPEX per year (screening).
_OPEX_PCT_LO = 0.015
_OPEX_PCT_HI = 0.025

# Default project life for simple payback / LCOE (years).
_PROJECT_LIFE_Y = 25


@dataclass
class RevenueIQRequest:
    country: str = ""
    land_use: str = "Standard"
    mount_type: str = "Fixed Tilt"
    dc_kwp: float = 0.0
    annual_mwh: float = 0.0
    terrain_grade: str = "good"
    lat: Optional[float] = None
    lon: Optional[float] = None
    project_name: str = ""


@dataclass
class RevenueIQResult:
    success: bool
    currency_display: str = "EUR"
    tariff_label: str = ""
    tariff_notes: str = ""
    revenue_eur_mwh_lo: float = 0.0
    revenue_eur_mwh_hi: float = 0.0
    annual_revenue_eur_lo: float = 0.0
    annual_revenue_eur_hi: float = 0.0
    capex_eur_wp_lo: float = 0.0
    capex_eur_wp_hi: float = 0.0
    total_capex_eur_lo: float = 0.0
    total_capex_eur_hi: float = 0.0
    opex_eur_yr_lo: float = 0.0
    opex_eur_yr_hi: float = 0.0
    payback_years_lo: Optional[float] = None
    payback_years_hi: Optional[float] = None
    lcoe_eur_mwh_lo: Optional[float] = None
    lcoe_eur_mwh_hi: Optional[float] = None
    screening_disclaimer: str = (
        "Screening-grade economics only — not a bankable financial model. "
        "Tariffs, CAPEX, and OPEX are indicative bands."
    )
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "currency_display": self.currency_display,
            "tariff": {
                "label": self.tariff_label,
                "notes": self.tariff_notes,
                "revenue_eur_mwh_lo": self.revenue_eur_mwh_lo,
                "revenue_eur_mwh_hi": self.revenue_eur_mwh_hi,
            },
            "annual_revenue_eur_lo": self.annual_revenue_eur_lo,
            "annual_revenue_eur_hi": self.annual_revenue_eur_hi,
            "capex": {
                "eur_per_wp_lo": self.capex_eur_wp_lo,
                "eur_per_wp_hi": self.capex_eur_wp_hi,
                "total_eur_lo": self.total_capex_eur_lo,
                "total_eur_hi": self.total_capex_eur_hi,
            },
            "opex_eur_yr_lo": self.opex_eur_yr_lo,
            "opex_eur_yr_hi": self.opex_eur_yr_hi,
            "payback_years_lo": self.payback_years_lo,
            "payback_years_hi": self.payback_years_hi,
            "lcoe_eur_mwh_lo": self.lcoe_eur_mwh_lo,
            "lcoe_eur_mwh_hi": self.lcoe_eur_mwh_hi,
            "screening_disclaimer": self.screening_disclaimer,
            "errors": self.errors,
        }


def _simple_payback(capex: float, net_annual: float) -> Optional[float]:
    if capex <= 0 or net_annual <= 0:
        return None
    return round(capex / net_annual, 1)


def _lcoe_eur_mwh(capex: float, annual_mwh: float, opex_yr: float, life_y: int = _PROJECT_LIFE_Y) -> Optional[float]:
    """Levelised cost — simplified, no discount rate (screening headline)."""
    if capex <= 0 or annual_mwh <= 0 or life_y <= 0:
        return None
    total_energy = annual_mwh * life_y
    total_cost = capex + opex_yr * life_y
    return round(total_cost / total_energy, 1)


def run_revenue_analysis(req: RevenueIQRequest) -> RevenueIQResult:
    """Compute screening revenue, CAPEX band, payback, and LCOE from layout + yield inputs."""
    out = RevenueIQResult(success=False)

    if req.dc_kwp <= 0:
        out.errors.append("DC capacity (kWp) required — run LayoutIQ first.")
    if req.annual_mwh <= 0:
        out.errors.append("Annual energy (MWh) required — run YieldIQ first.")
    if out.errors:
        return out

    band = resolve_tariff(req.country, req.land_use)
    rev_lo, rev_hi = tariff_eur_mwh(band)
    out.tariff_label = band.label
    out.tariff_notes = band.notes
    out.revenue_eur_mwh_lo = round(rev_lo, 1)
    out.revenue_eur_mwh_hi = round(rev_hi, 1)

    out.annual_revenue_eur_lo = round(req.annual_mwh * rev_lo, 0)
    out.annual_revenue_eur_hi = round(req.annual_mwh * rev_hi, 0)

    wp_lo, wp_hi = capex_band_eur_wp(req.mount_type, req.land_use, req.terrain_grade)
    out.capex_eur_wp_lo = wp_lo
    out.capex_eur_wp_hi = wp_hi
    cap_lo, cap_hi = total_capex_eur(req.dc_kwp, wp_lo, wp_hi)
    out.total_capex_eur_lo = cap_lo
    out.total_capex_eur_hi = cap_hi

    out.opex_eur_yr_lo = round(cap_lo * _OPEX_PCT_LO, 0)
    out.opex_eur_yr_hi = round(cap_hi * _OPEX_PCT_HI, 0)

    # Payback: optimistic = low CAPEX / high net revenue; conservative opposite.
    net_lo = out.annual_revenue_eur_lo - out.opex_eur_yr_hi
    net_hi = out.annual_revenue_eur_hi - out.opex_eur_yr_lo
    out.payback_years_lo = _simple_payback(cap_lo, net_hi)  # best case
    out.payback_years_hi = _simple_payback(cap_hi, net_lo)  # worst case

    out.lcoe_eur_mwh_lo = _lcoe_eur_mwh(cap_lo, req.annual_mwh, out.opex_eur_yr_lo)
    out.lcoe_eur_mwh_hi = _lcoe_eur_mwh(cap_hi, req.annual_mwh, out.opex_eur_yr_hi)

    out.success = True
    return out
