"""Screening-grade CAPEX bands (€/Wp) by mount, land use, and terrain grade."""

from __future__ import annotations

from typing import Tuple

# €/Wp installed DC — EPC screening bands (EU/global ground-mount, 2025–2026).
_CAPEX_EUR_WP: dict[tuple[str, str], tuple[float, float]] = {
    ("Fixed Tilt", "Standard"): (0.52, 0.72),
    ("Single-Axis Tracker", "Standard"): (0.62, 0.82),
    ("Fixed Tilt", "Agri-PV"): (0.58, 0.78),
    ("Single-Axis Tracker", "Agri-PV"): (0.68, 0.88),
}

# Terrain grade uplifts on civil / pile cost.
_TERRAIN_UPLIFT = {
    "excellent": 1.0,
    "good": 1.0,
    "acceptable": 1.03,
    "challenging": 1.08,
    "critical": 1.15,
}


def capex_band_eur_wp(
    mount_type: str,
    land_use: str,
    terrain_grade: str = "good",
) -> Tuple[float, float]:
    """Return (lo, hi) €/Wp for installed DC."""
    mount = mount_type if mount_type in ("Fixed Tilt", "Single-Axis Tracker") else "Fixed Tilt"
    lu = land_use if land_use in ("Standard", "Agri-PV") else "Standard"
    lo, hi = _CAPEX_EUR_WP.get((mount, lu), (0.55, 0.75))
    uplift = _TERRAIN_UPLIFT.get((terrain_grade or "good").lower(), 1.05)
    return round(lo * uplift, 3), round(hi * uplift, 3)


def total_capex_eur(dc_kwp: float, eur_per_wp_lo: float, eur_per_wp_hi: float) -> Tuple[float, float]:
    if dc_kwp <= 0:
        return 0.0, 0.0
    wp = dc_kwp * 1000.0
    return round(wp * eur_per_wp_lo, 0), round(wp * eur_per_wp_hi, 0)
