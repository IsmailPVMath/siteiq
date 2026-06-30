"""Site suitability scoring for unified PDF reports (ported from pages/siteiq.py)."""

from __future__ import annotations

from pvmath_capacity import format_mwp_range
from pvmath_screening_library import calculate_pvmath_score, get_verdict_from_score

from pvmath_workflow.score_config import SUITABILITY_WEIGHTS_PARTIAL as SUITABILITY_WEIGHTS


def _slope_quality_tier(pct, mount_type="Fixed Tilt") -> int:
    if pct is None:
        return 1
    if mount_type == "Single-Axis Tracker":
        if pct <= 3:
            return 5
        if pct <= 6:
            return 3
        if pct <= 10:
            return 2
        return 0
    if pct <= 5:
        return 5
    if pct <= 10:
        return 3
    if pct <= 15:
        return 2
    return 0


def _param_tier(lbl: str) -> int:
    if "❌" in lbl:
        return 0
    if "Data unavailable" in lbl:
        return 1
    if "(Indicative)" in lbl or "Indicative only" in lbl:
        if "Excellent" in lbl:
            return 5
        if "Good" in lbl:
            return 4
        if "Acceptable" in lbl or "Moderate" in lbl:
            return 3
        if "Challenging" in lbl:
            return 2
        if "Critical" in lbl or "Poor" in lbl:
            return 0
        return 3
    if "Challenging" in lbl:
        return 2
    if "Acceptable" in lbl or "Moderate" in lbl:
        return 3
    if "Good" in lbl:
        return 4
    if "Excellent" in lbl:
        return 5
    return 3


def _tier_to_score(tier: int, *, indicative: bool = False, terrainiq: bool = False) -> int:
    base = {5: 95, 4: 88, 3: 75, 2: 55, 1: 50, 0: 30}.get(tier, 70)
    if terrainiq and tier >= 4:
        return min(98, base + 2)
    if indicative and tier >= 4:
        return max(50, base - 5)
    return base


def _ghi_to_score(ghi) -> int:
    try:
        g = float(ghi)
    except (TypeError, ValueError):
        return 50
    if g >= 2200:
        return 98
    if g >= 2000:
        return 95
    if g >= 1800:
        return 90
    if g >= 1600:
        return 85
    if g >= 1300:
        return 80
    if g >= 1100:
        return 70
    if g >= 900:
        return 55
    return 40


def _flood_risk_to_score(flood_risk: str) -> int:
    r = (flood_risk or "").upper()
    if "HIGH" in r and "LOW" not in r:
        return 40
    if "MODERATE" in r and "LOW" not in r:
        return 60
    if "LOW-MOD" in r or "LOW-MODERATE" in r:
        return 70
    if "LOW" in r:
        return 90
    return 50


def _land_use_to_score(land_use: str) -> int:
    return 85 if land_use == "Agri-PV" else 90


def _regulatory_to_score(country: str, eeg_status: str, project_country: str) -> int:
    c = (project_country or country or "").lower()
    status = (eeg_status or "").lower()
    _strong = (
        "germany", "deutschland", "united states", "usa", "america",
        "spain", "france", "italy", "australia", "india", "united kingdom",
    )
    if any(x in c for x in _strong) and status and "check local" not in status:
        return 85
    if status and any(w in status for w in ("applicable", "eligible", "auction", "itc", "eeg")):
        return 80
    return 70


def compute_site_suitability(
    solar_lbl,
    slope_lbl,
    flood_risk,
    land_use,
    solar,
    terrain,
    mount_type="Fixed Tilt",
    country="",
    eeg_status="",
    project_country="",
    cap=None,
) -> dict:
    solar_tier = _param_tier(solar_lbl)
    if (terrain.get("terrainiq_confirmed") or terrain.get("topoiq_confirmed")) and terrain.get("mean_slope_pct") is not None:
        slope_tier = _slope_quality_tier(terrain["mean_slope_pct"], mount_type)
        terrain_indicative = False
        terrain_terrainiq = True
    elif "(Indicative)" in slope_lbl or terrain.get("boundary_sampled"):
        pct = terrain.get("mean_slope_pct") or terrain.get("max_slope_pct")
        slope_tier = _slope_quality_tier(pct, mount_type) if pct is not None else _param_tier(slope_lbl)
        terrain_indicative = True
        terrain_terrainiq = False
    else:
        slope_tier = _param_tier(slope_lbl)
        terrain_indicative = False
        terrain_terrainiq = False

    solar_score = _ghi_to_score(solar.get("annual_ghi") if solar.get("success") else None)
    if solar_tier < 4 and solar.get("success"):
        solar_score = min(solar_score, _tier_to_score(solar_tier))

    terrain_score = _tier_to_score(
        slope_tier, indicative=terrain_indicative, terrainiq=terrain_terrainiq,
    )
    flood_score = _flood_risk_to_score(flood_risk)
    land_score = _land_use_to_score(land_use)
    reg_score = _regulatory_to_score(country, eeg_status, project_country)

    raw = {
        "solar": solar_score,
        "terrain": terrain_score,
        "flood": flood_score,
        "land": land_score,
        "regulatory": reg_score,
    }
    overall = calculate_pvmath_score(raw)

    drivers = []
    if solar.get("success"):
        ghi = solar.get("annual_ghi")
        if ghi is not None and float(ghi) >= 1300:
            drivers.append(("positive", f"Excellent solar resource ({float(ghi):,.1f} kWh/m²/yr)"))
        elif ghi is not None:
            drivers.append(("positive", f"Solar resource {float(ghi):,.1f} kWh/m²/yr"))

    if terrain.get("success"):
        if (terrain.get("terrainiq_confirmed") or terrain.get("topoiq_confirmed")) and terrain.get("mean_slope_pct") is not None:
            drivers.append((
                "positive",
                f"Low terrain constraints (mean slope {terrain['mean_slope_pct']:.1f}%)",
            ))
        elif terrain.get("max_slope_pct") is not None and float(terrain["max_slope_pct"]) <= 6:
            drivers.append((
                "positive",
                f"Favourable sample slope ({terrain['max_slope_pct']:.1f}% max in screening sample)",
            ))

    if cap and cap.get("mwp_lo") is not None:
        drivers.append((
            "positive",
            f"Utility-scale development potential ({format_mwp_range(cap['mwp_lo'], cap['mwp_hi'])})",
        ))

    drivers.append(("warn", "Flood assessment based on screening-level data only"))
    if terrain.get("boundary_sampled") and not (terrain.get("terrainiq_confirmed") or terrain.get("topoiq_confirmed")):
        drivers.append(("warn", "Terrain confirmation recommended via TerrainIQ"))

    return {
        "scores": raw,
        "overall": overall,
        "verdict_label": get_verdict_from_score(overall),
        "drivers": drivers,
        "pvmath_score": overall,
    }
