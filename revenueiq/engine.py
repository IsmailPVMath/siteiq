"""RevenueIQ screening engine — CAPEX, OPEX, revenue, IRR, NPV, LCOE, sensitivity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from revenueiq.capex import compute_capex
from revenueiq.currency import country_iso, currency_code, eur_fx_rate, to_local
from revenueiq.tariffs import resolve_tariff

_DEGRADATION = 0.0045
_YIELD_UNCERTAINTY = 0.07

MARKET_IRR_FLOOR: dict[str, float] = {
    "DE": 5.0,
    "AT": 5.0,
    "CH": 5.5,
    "ES": 7.0,
    "IT": 7.0,
    "FR": 6.5,
    "PL": 6.5,
    "IN": 9.0,
    "US": 7.5,
    "AU": 7.5,
    "default": 6.0,
}

_DEFAULT_WACC: dict[str, float] = {
    "DE": 6.75,
    "AT": 6.75,
    "ES": 7.25,
    "IT": 7.25,
    "FR": 7.25,
    "PL": 8.25,
    "IN": 10.5,
    "AU": 8.0,
    "US": 7.5,
}

_LAND_LEASE_EUR_HA: dict[str, dict[str, tuple[float, float]]] = {
    "DE": {"Standard": (1200, 2500), "Agri-PV": (600, 1200)},
    "AT": {"Standard": (1000, 2000), "Agri-PV": (500, 1000)},
    "ES": {"Standard": (400, 900), "Agri-PV": (200, 500)},
    "IT": {"Standard": (500, 1000), "Agri-PV": (250, 600)},
    "FR": {"Standard": (400, 800), "Agri-PV": (200, 400)},
    "PL": {"Standard": (300, 700), "Agri-PV": (150, 350)},
    "IN": {"Standard": (100, 250), "Agri-PV": (100, 250)},
    "AU": {"Standard": (200, 500), "Agri-PV": (200, 500)},
    "US": {"Standard": (300, 700), "Agri-PV": (300, 700)},
}

_DISCLAIMER = (
    "RevenueIQ provides indicative financial screening only. CAPEX ranges are based on "
    "global benchmark data (2025–2026) adjusted for technology type, mount system, country, "
    "and market conditions; actual costs depend on site conditions, supply chain, and competitive "
    "EPC tender results. Revenue figures use indicative tariff and PPA benchmark rates — "
    "government auction projects must win the applicable tender round, and PPA rates depend on "
    "offtaker credit and market conditions at the time of contract. US ITC figures are indicative; "
    "eligibility and percentage depend on compliance with IRA 2022 requirements. All financial "
    "metrics (IRR, NPV, LCOE, payback) are screening-grade estimates only and are not bankable "
    "yield assessments. Engage a certified financial advisor and independent engineer before "
    "making any financial close or investment decision."
)


@dataclass
class RevenueIQRequest:
    country: str = ""
    land_use: str = "Standard"
    mount_type: str = "Fixed Tilt"
    dc_kwp: float = 0.0
    annual_mwh: float = 0.0
    site_area_ha: float = 0.0
    mean_slope_pct: Optional[float] = None
    grid_distance_km: Optional[float] = None
    terrain_grade: str = "good"
    wacc_pct: float = 6.5
    project_lifetime_yr: int = 25
    tariff_override_local_mwh: Optional[float] = None
    capex_override_eur_kwp: Optional[float] = None
    itc_rate: float = 0.0
    lat: Optional[float] = None
    lon: Optional[float] = None
    project_name: str = ""


@dataclass
class RevenueIQResult:
    success: bool = False
    errors: list[str] = field(default_factory=list)
    local_currency: str = "EUR"
    eur_fx_rate: float = 1.0
    capex_lo_eur: float = 0.0
    capex_hi_eur: float = 0.0
    capex_lo_local: float = 0.0
    capex_hi_local: float = 0.0
    itc_credit_eur: float = 0.0
    effective_capex_lo_eur: float = 0.0
    effective_capex_hi_eur: float = 0.0
    capex_breakdown: dict = field(default_factory=dict)
    opex_lo_eur_yr: float = 0.0
    opex_hi_eur_yr: float = 0.0
    opex_lo_local_yr: float = 0.0
    opex_hi_local_yr: float = 0.0
    tariff_mode: str = "PPA"
    tariff_lo_eur_mwh: float = 0.0
    tariff_hi_eur_mwh: float = 0.0
    tariff_lo_local_mwh: float = 0.0
    tariff_hi_local_mwh: float = 0.0
    tariff_label: str = ""
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
    sensitivity: dict = field(default_factory=dict)
    viability: str = "MARGINAL"
    viability_note: str = ""
    economic_score: int = 50
    wacc_pct: float = 6.5
    screening_disclaimer: str = _DISCLAIMER

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


def _slope_from_grade(terrain_grade: str) -> float:
    return {
        "excellent": 1.0,
        "good": 3.0,
        "acceptable": 6.0,
        "challenging": 8.0,
        "critical": 12.0,
    }.get((terrain_grade or "good").lower(), 4.0)


def _default_wacc(country: str) -> float:
    iso = country_iso(country)
    return _DEFAULT_WACC.get(iso, 6.5)


def _default_itc(country: str, itc_rate: float) -> float:
    if itc_rate > 0:
        return min(1.0, itc_rate)
    if country_iso(country) == "US":
        return 0.30
    return 0.0


def _land_lease_eur_ha(country: str, land_use: str) -> tuple[float, float]:
    iso = country_iso(country)
    lu = land_use if land_use in ("Standard", "Agri-PV") else "Standard"
    row = _LAND_LEASE_EUR_HA.get(iso, {"Standard": (250, 600), "Agri-PV": (150, 400)})
    return row.get(lu, row["Standard"])


def _compute_opex(
    *,
    dc_kwp: float,
    gross_capex_mid: float,
    mount_type: str,
    country: str,
    land_use: str,
    site_area_ha: float,
) -> tuple[float, float]:
    is_sat = mount_type == "Single-Axis Tracker"
    om_lo = 8.0 * dc_kwp
    om_hi = (14.0 + (2.0 if is_sat else 0.0)) * dc_kwp
    lease_lo, lease_hi = _land_lease_eur_ha(country, land_use)
    area = max(site_area_ha, dc_kwp / 800.0) if site_area_ha <= 0 else site_area_ha
    land_lo = lease_lo * area
    land_hi = lease_hi * area
    ins_lo = gross_capex_mid * 0.0025
    ins_hi = gross_capex_mid * 0.004
    am_lo = 2.0 * dc_kwp
    am_hi = 4.0 * dc_kwp
    grid_lo = 1.0 * dc_kwp
    grid_hi = 3.0 * dc_kwp
    opex_lo = om_lo + land_lo + ins_lo + am_lo + grid_lo
    opex_hi = om_hi + land_hi + ins_hi + am_hi + grid_hi
    return round(opex_lo, 0), round(opex_hi, 0)


def _year_mwh(annual_mwh: float, year: int) -> float:
    return annual_mwh * ((1 - _DEGRADATION) ** year)


def _lifetime_energy(annual_mwh: float, life: int) -> float:
    return sum(_year_mwh(annual_mwh, y) for y in range(life))


def _revenue_yr1(tariff: float, mwh: float) -> float:
    return tariff * mwh


def _cumulative_revenue(tariff: float, annual_mwh: float, life: int) -> float:
    return sum(_revenue_yr1(tariff, _year_mwh(annual_mwh, y)) for y in range(life))


def _npv_opex(opex: float, wacc: float, life: int) -> float:
    r = wacc / 100.0
    return sum(opex / ((1 + r) ** (y + 1)) for y in range(life))


def _cashflows(
    capex: float,
    annual_mwh: float,
    tariff: float,
    opex: float,
    life: int,
) -> list[float]:
    flows = [-capex]
    for y in range(life):
        rev = _revenue_yr1(tariff, _year_mwh(annual_mwh, y))
        flows.append(rev - opex)
    return flows


def _npv(cashflows: list[float], wacc: float) -> float:
    r = wacc / 100.0
    return sum(cf / ((1 + r) ** t) for t, cf in enumerate(cashflows))


def _irr(cashflows: list[float]) -> Optional[float]:
    if not cashflows or cashflows[0] >= 0:
        return None
    rate = 0.08
    for _ in range(80):
        npv = sum(cf / ((1 + rate) ** t) for t, cf in enumerate(cashflows))
        dnpv = sum(
            -t * cf / ((1 + rate) ** (t + 1))
            for t, cf in enumerate(cashflows)
            if t > 0
        )
        if abs(dnpv) < 1e-12:
            break
        rate = rate - npv / dnpv
        rate = max(-0.5, min(2.0, rate))
        if abs(npv) < 1e-4:
            break
    if rate <= -0.49 or rate > 1.99:
        return None
    return round(rate * 100, 2)


def _lcoe(capex: float, opex_yr: float, annual_mwh: float, wacc: float, life: int) -> float:
    energy = _lifetime_energy(annual_mwh, life)
    if energy <= 0:
        return 0.0
    npv_o = _npv_opex(opex_yr, wacc, life)
    return (capex + npv_o) / energy


def _economic_score(
    irr_lo: Optional[float],
    irr_hi: Optional[float],
    lcoe_hi: float,
    tariff_lo: float,
    lcoe_lo: float,
    tariff_hi: float,
) -> int:
    if irr_lo is None and irr_hi is None:
        return 50
    best_irr = irr_hi if irr_hi is not None else irr_lo
    worst_irr = irr_lo if irr_lo is not None else irr_hi
    if worst_irr is not None and worst_irr > 8 and lcoe_hi < tariff_lo:
        return 95
    if best_irr is not None and best_irr > 8 and lcoe_lo < tariff_hi:
        return 90
    if worst_irr is not None and worst_irr >= 5:
        return 78
    if worst_irr is not None and worst_irr >= 3:
        return 58
    if worst_irr is not None and worst_irr < 3:
        return 35
    return 50


def _viability_verdict(
    *,
    lcoe_lo: float,
    lcoe_hi: float,
    tariff_lo: float,
    tariff_hi: float,
    irr_lo: Optional[float],
    irr_hi: Optional[float],
    country: str,
) -> tuple[str, str]:
    iso = country_iso(country)
    floor = MARKET_IRR_FLOOR.get(iso, MARKET_IRR_FLOOR.get("default", 6.0))

    if lcoe_lo > tariff_hi or (irr_hi is not None and irr_hi < floor - 3):
        state = "THIN"
        text = "Thin margin — validate assumptions before advancing"
    elif lcoe_hi < tariff_lo and irr_lo is not None and irr_lo > floor:
        state = "STRONG"
        text = "Strong economic case — proceed to FEED"
    elif irr_lo is not None and floor - 3 <= irr_lo <= floor:
        state = "MARGINAL"
        text = "Marginal — de-risk CAPEX and grid cost before committing"
    elif lcoe_lo <= tariff_hi <= lcoe_hi or (tariff_lo <= lcoe_hi <= tariff_hi):
        state = "MARGINAL"
        text = "Marginal — de-risk CAPEX and grid cost before committing"
    elif irr_lo is not None and irr_lo > floor:
        state = "STRONG"
        text = "Strong economic case — proceed to FEED"
    else:
        state = "MARGINAL"
        text = "Marginal — de-risk CAPEX and grid cost before committing"

    note = (
        f"At €{lcoe_lo:.0f}–{lcoe_hi:.0f}/MWh LCOE vs €{tariff_lo:.0f}–{tariff_hi:.0f}/MWh "
        f"available tariff, {text.lower()}."
    )
    return state, note


def _sensitivity(
    *,
    capex_mid: float,
    annual_mwh: float,
    tariff_mid: float,
    opex_mid: float,
    wacc: float,
    life: int,
) -> dict[str, float]:
    base_cf = _cashflows(capex_mid, annual_mwh, tariff_mid, opex_mid, life)
    base_irr = _irr(base_cf)
    if base_irr is None:
        return {"yield": 0.0, "capex": 0.0, "tariff": 0.0, "opex": 0.0}

    def delta(var: str) -> float:
        shifts = []
        for sign in (-1, 1):
            mwh = annual_mwh * (1 + sign * 0.1) if var == "yield" else annual_mwh
            cap = capex_mid * (1 + sign * 0.1) if var == "capex" else capex_mid
            tar = tariff_mid * (1 + sign * 0.1) if var == "tariff" else tariff_mid
            op = opex_mid * (1 + sign * 0.1) if var == "opex" else opex_mid
            irr = _irr(_cashflows(cap, mwh, tar, op, life))
            if irr is not None:
                shifts.append(abs(irr - base_irr))
        return round(max(shifts) if shifts else 0.0, 2)

    return {k: delta(k) for k in ("yield", "capex", "tariff", "opex")}


def run_revenue_analysis(req: RevenueIQRequest) -> RevenueIQResult:
    out = RevenueIQResult(success=False)

    if req.dc_kwp <= 0:
        out.errors.append("DC capacity (kWp) required — run LayoutIQ first.")
    if req.annual_mwh <= 0:
        out.errors.append("Annual energy (MWh) required — run YieldIQ first.")
    if out.errors:
        return out

    iso = country_iso(req.country)
    out.local_currency = currency_code(req.country)
    out.eur_fx_rate = eur_fx_rate(req.country)

    slope = req.mean_slope_pct if req.mean_slope_pct is not None else _slope_from_grade(req.terrain_grade)
    itc = _default_itc(req.country, req.itc_rate)
    wacc = req.wacc_pct if req.wacc_pct != 6.5 else _default_wacc(req.country)
    out.wacc_pct = wacc
    life = max(1, min(40, int(req.project_lifetime_yr or 25)))

    capex = compute_capex(
        dc_kwp=req.dc_kwp,
        mount_type=req.mount_type,
        land_use=req.land_use,
        country=req.country,
        mean_slope_pct=slope,
        grid_distance_km=req.grid_distance_km,
        capex_override_eur_kwp=req.capex_override_eur_kwp,
        itc_rate=itc,
    )
    out.capex_lo_eur = capex["capex_lo_eur"]
    out.capex_hi_eur = capex["capex_hi_eur"]
    out.capex_lo_local = capex["capex_lo_local"]
    out.capex_hi_local = capex["capex_hi_local"]
    out.effective_capex_lo_eur = capex["effective_capex_lo_eur"]
    out.effective_capex_hi_eur = capex["effective_capex_hi_eur"]
    out.itc_credit_eur = capex["itc_credit_eur"]
    out.capex_breakdown = capex["capex_breakdown"]

    gross_mid = (out.capex_lo_eur + out.capex_hi_eur) / 2
    opex_lo, opex_hi = _compute_opex(
        dc_kwp=req.dc_kwp,
        gross_capex_mid=gross_mid,
        mount_type=req.mount_type,
        country=req.country,
        land_use=req.land_use,
        site_area_ha=req.site_area_ha,
    )
    out.opex_lo_eur_yr = opex_lo
    out.opex_hi_eur_yr = opex_hi
    out.opex_lo_local_yr = round(to_local(opex_lo, req.country), 0)
    out.opex_hi_local_yr = round(to_local(opex_hi, req.country), 0)

    tariff = resolve_tariff(
        req.country,
        req.land_use,
        tariff_override_local_mwh=req.tariff_override_local_mwh,
    )
    out.tariff_mode = tariff.tariff_mode
    out.tariff_lo_eur_mwh = tariff.tariff_lo_eur_mwh
    out.tariff_hi_eur_mwh = tariff.tariff_hi_eur_mwh
    out.tariff_lo_local_mwh = tariff.tariff_lo_local_mwh
    out.tariff_hi_local_mwh = tariff.tariff_hi_local_mwh
    out.tariff_label = tariff.label

    mwh_lo = req.annual_mwh * (1 - _YIELD_UNCERTAINTY)
    mwh_hi = req.annual_mwh * (1 + _YIELD_UNCERTAINTY)

    out.revenue_yr1_lo_eur = round(_revenue_yr1(tariff.tariff_lo_eur_mwh, mwh_lo), 0)
    out.revenue_yr1_hi_eur = round(_revenue_yr1(tariff.tariff_hi_eur_mwh, mwh_hi), 0)
    out.revenue_25yr_lo_eur = round(
        _cumulative_revenue(tariff.tariff_lo_eur_mwh, mwh_lo, life), 0
    )
    out.revenue_25yr_hi_eur = round(
        _cumulative_revenue(tariff.tariff_hi_eur_mwh, mwh_hi, life), 0
    )

    eff_lo = out.effective_capex_lo_eur
    eff_hi = out.effective_capex_hi_eur

    energy_central = _lifetime_energy(req.annual_mwh, life)
    out.lcoe_lo_eur_mwh = round(
        (eff_lo + _npv_opex(opex_lo, wacc, life)) / energy_central, 1
    )
    out.lcoe_hi_eur_mwh = round(
        (eff_hi + _npv_opex(opex_hi, wacc, life)) / energy_central, 1
    )

    rev_lo = out.revenue_yr1_lo_eur
    rev_hi = out.revenue_yr1_hi_eur
    if rev_hi > 0:
        out.payback_lo_yr = round(eff_lo / rev_hi, 1)
    if rev_lo > 0:
        out.payback_hi_yr = round(eff_hi / rev_lo, 1)

    opex_mid = (opex_lo + opex_hi) / 2
    irr_lo = _irr(_cashflows(eff_hi, req.annual_mwh, tariff.tariff_lo_eur_mwh, opex_mid, life))
    irr_hi = _irr(_cashflows(eff_lo, req.annual_mwh, tariff.tariff_hi_eur_mwh, opex_mid, life))
    out.irr_lo_pct = irr_lo
    out.irr_hi_pct = irr_hi

    npv_lo = _npv(_cashflows(eff_hi, req.annual_mwh, tariff.tariff_lo_eur_mwh, opex_mid, life), wacc)
    npv_hi = _npv(_cashflows(eff_lo, req.annual_mwh, tariff.tariff_hi_eur_mwh, opex_mid, life), wacc)
    out.npv_lo_eur = round(npv_lo, 0)
    out.npv_hi_eur = round(npv_hi, 0)

    capex_mid = (eff_lo + eff_hi) / 2
    opex_mid = (opex_lo + opex_hi) / 2
    tariff_mid = (tariff.tariff_lo_eur_mwh + tariff.tariff_hi_eur_mwh) / 2
    out.sensitivity = _sensitivity(
        capex_mid=capex_mid,
        annual_mwh=req.annual_mwh,
        tariff_mid=tariff_mid,
        opex_mid=opex_mid,
        wacc=wacc,
        life=life,
    )

    out.viability, out.viability_note = _viability_verdict(
        lcoe_lo=out.lcoe_lo_eur_mwh,
        lcoe_hi=out.lcoe_hi_eur_mwh,
        tariff_lo=tariff.tariff_lo_eur_mwh,
        tariff_hi=tariff.tariff_hi_eur_mwh,
        irr_lo=irr_lo,
        irr_hi=irr_hi,
        country=req.country,
    )
    out.economic_score = _economic_score(
        irr_lo, irr_hi, out.lcoe_hi_eur_mwh, tariff.tariff_lo_eur_mwh,
        out.lcoe_lo_eur_mwh, tariff.tariff_hi_eur_mwh,
    )
    out.success = True
    return out
