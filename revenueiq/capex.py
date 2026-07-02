"""Screening-grade CAPEX model — 10-component breakdown with country / terrain / grid adjustments."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from revenueiq.currency import country_iso, eur_fx_rate, to_local

# €/kWp DC component bands (2026 global benchmarks).
_BASE_COMPONENTS_FT: dict[str, tuple[float, float]] = {
    "pv_modules": (130, 170),
    "inverters": (40, 65),
    "mounting_structure": (55, 85),
    "dc_cabling": (20, 35),
    "ac_cabling": (25, 45),
    "engineering": (15, 25),
    "permitting": (10, 20),
    "commissioning": (8, 15),
}

_BASE_COMPONENTS_SAT: dict[str, tuple[float, float]] = {
    "pv_modules": (130, 170),
    "inverters": (40, 65),
    "mounting_structure": (130, 170),
    "dc_cabling": (20, 35),
    "ac_cabling": (25, 45),
    "engineering": (15, 25),
    "permitting": (10, 20),
    "commissioning": (8, 15),
}

_COUNTRY_MULT: dict[str, tuple[float, float]] = {
    "DE": (1.15, 1.25),
    "AT": (1.15, 1.25),
    "CH": (1.15, 1.25),
    "ES": (1.00, 1.00),
    "IT": (1.00, 1.00),
    "FR": (1.00, 1.00),
    "PL": (1.00, 1.00),
    "IN": (0.72, 0.88),
    "AU": (0.80, 0.95),
    "US": (1.10, 1.20),
}

_DEFAULT_COUNTRY_MULT = (1.00, 1.00)
_CONTINGENCY = 0.05


def _civil_band(
    mean_slope_pct: Optional[float],
    mount_type: str,
) -> tuple[float, float]:
    """Civil / earthworks €/kWp from mean slope (%)."""
    is_sat = mount_type == "Single-Axis Tracker"
    slope = mean_slope_pct if mean_slope_pct is not None else 4.0
    if slope <= 2:
        return (30, 55) if is_sat else (25, 45)
    if slope <= 5:
        return (55, 90) if is_sat else (45, 75)
    if slope <= 10:
        return (90, 160) if is_sat else (75, 130)
    return (160, 220) if is_sat else (130, 200)


def _grid_band(grid_distance_km: Optional[float]) -> tuple[float, float]:
    if grid_distance_km is None:
        return 50.0, 80.0
    d = max(0.0, float(grid_distance_km))
    if d < 1:
        return 15, 30
    if d < 3:
        return 30, 60
    if d < 7:
        return 60, 120
    return 120, 200


def _agri_mult(land_use: str) -> tuple[float, float]:
    if land_use == "Agri-PV":
        return 1.5, 1.8
    return 1.0, 1.0


def compute_capex(
    *,
    dc_kwp: float,
    mount_type: str,
    land_use: str,
    country: str,
    mean_slope_pct: Optional[float] = None,
    grid_distance_km: Optional[float] = None,
    capex_override_eur_kwp: Optional[float] = None,
    itc_rate: float = 0.0,
) -> dict[str, Any]:
    """Return gross/effective CAPEX bands and per-component breakdown in EUR + local."""
    if dc_kwp <= 0:
        empty: dict[str, Any] = {
            "capex_lo_eur": 0.0,
            "capex_hi_eur": 0.0,
            "capex_lo_local": 0.0,
            "capex_hi_local": 0.0,
            "effective_capex_lo_eur": 0.0,
            "effective_capex_hi_eur": 0.0,
            "itc_credit_eur": 0.0,
            "capex_breakdown": {},
            "capex_lo_eur_kwp": 0.0,
            "capex_hi_eur_kwp": 0.0,
        }
        return empty

    mount = mount_type if mount_type in ("Fixed Tilt", "Single-Axis Tracker") else "Fixed Tilt"
    lu = land_use if land_use in ("Standard", "Agri-PV") else "Standard"
    base = _BASE_COMPONENTS_SAT if mount == "Single-Axis Tracker" else _BASE_COMPONENTS_FT
    iso = country_iso(country)
    country_lo, country_hi = _COUNTRY_MULT.get(iso, _DEFAULT_COUNTRY_MULT)
    agri_mount_lo, agri_mount_hi = _agri_mult(lu)
    civil_lo, civil_hi = _civil_band(mean_slope_pct, mount)
    if lu == "Agri-PV":
        civil_lo *= 1.2
        civil_hi *= 1.3
    grid_lo, grid_hi = _grid_band(grid_distance_km)

    comp_lo: dict[str, float] = {}
    comp_hi: dict[str, float] = {}
    for name, (lo, hi) in base.items():
        if name == "mounting_structure":
            comp_lo[name] = lo * agri_mount_lo
            comp_hi[name] = hi * agri_mount_hi
        else:
            comp_lo[name] = lo
            comp_hi[name] = hi
    comp_lo["civil_works"] = civil_lo
    comp_hi["civil_works"] = civil_hi
    comp_lo["grid_connection"] = grid_lo
    comp_hi["grid_connection"] = grid_hi

    sub_lo = sum(comp_lo.values())
    sub_hi = sum(comp_hi.values())
    pre_lo = sub_lo * (1 + _CONTINGENCY) * country_lo
    pre_hi = sub_hi * (1 + _CONTINGENCY) * country_hi

    if capex_override_eur_kwp is not None and capex_override_eur_kwp > 0:
        pre_lo = pre_hi = float(capex_override_eur_kwp)

    gross_lo = pre_lo * dc_kwp
    gross_hi = pre_hi * dc_kwp

    itc = max(0.0, min(1.0, itc_rate))
    itc_credit_lo = gross_lo * itc
    itc_credit_hi = gross_hi * itc
    eff_lo = gross_lo - itc_credit_lo
    eff_hi = gross_hi - itc_credit_hi

    fx = eur_fx_rate(country)
    breakdown: dict[str, dict[str, float]] = {}
    scale_lo = pre_lo / sub_lo if sub_lo > 0 else 1.0
    scale_hi = pre_hi / sub_hi if sub_hi > 0 else 1.0
    for name in comp_lo:
        row_lo = comp_lo[name] * scale_lo * dc_kwp
        row_hi = comp_hi[name] * scale_hi * dc_kwp
        breakdown[name] = {
            "lo_eur": round(row_lo, 0),
            "hi_eur": round(row_hi, 0),
            "lo_local": round(row_lo * fx, 0),
            "hi_local": round(row_hi * fx, 0),
        }

    return {
        "capex_lo_eur": round(gross_lo, 0),
        "capex_hi_eur": round(gross_hi, 0),
        "capex_lo_local": round(to_local(gross_lo, country), 0),
        "capex_hi_local": round(to_local(gross_hi, country), 0),
        "effective_capex_lo_eur": round(eff_lo, 0),
        "effective_capex_hi_eur": round(eff_hi, 0),
        "itc_credit_eur": round((itc_credit_lo + itc_credit_hi) / 2, 0),
        "itc_credit_lo_eur": round(itc_credit_lo, 0),
        "itc_credit_hi_eur": round(itc_credit_hi, 0),
        "capex_breakdown": breakdown,
        "capex_lo_eur_kwp": round(pre_lo, 1),
        "capex_hi_eur_kwp": round(pre_hi, 1),
    }


def capex_band_eur_wp(
    mount_type: str,
    land_use: str,
    terrain_grade: str = "good",
) -> Tuple[float, float]:
    """Legacy €/Wp helper for tests — maps terrain_grade to slope proxy."""
    grade_slope = {
        "excellent": 1.0,
        "good": 3.0,
        "acceptable": 6.0,
        "challenging": 8.0,
        "critical": 12.0,
    }
    slope = grade_slope.get((terrain_grade or "good").lower(), 4.0)
    cap = compute_capex(
        dc_kwp=1000.0,
        mount_type=mount_type,
        land_use=land_use,
        country="Germany",
        mean_slope_pct=slope,
    )
    lo = cap["capex_lo_eur"] / 1000.0 / 1000.0
    hi = cap["capex_hi_eur"] / 1000.0 / 1000.0
    return round(lo, 3), round(hi, 3)


def total_capex_eur(dc_kwp: float, eur_per_wp_lo: float, eur_per_wp_hi: float) -> Tuple[float, float]:
    if dc_kwp <= 0:
        return 0.0, 0.0
    wp = dc_kwp * 1000.0
    return round(wp * eur_per_wp_lo, 0), round(wp * eur_per_wp_hi, 0)
