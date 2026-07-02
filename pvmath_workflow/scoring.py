"""PVMath score helpers for the unified React workflow."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pvmath_workflow.score_config import (
    PVMATH_WEIGHTS_FULL,
    PVMATH_WEIGHTS_PARTIAL,
    calculate_pvmath_score,
    get_verdict_from_score,
    yield_bands_for_region,
    yield_region_key,
)

_TIER_SCORE = {
    "excellent": 95,
    "good": 82,
    "moderate": 65,
    "acceptable": 70,
    "challenging": 45,
    "critical": 20,
    "poor": 25,
    "unknown": 50,
    "low": 85,
    "low-moderate": 70,
    "high": 25,
}

_TERRAIN_CAP_MARGIN = 15


def tier_score(label: str) -> int:
    key = (label or "").lower().split()[0]
    for k, v in _TIER_SCORE.items():
        if k in key:
            return v
    return 55


def _interp_band(value: float, lo: float, hi: float, score_lo: float, score_hi: float) -> float:
    if hi <= lo:
        return score_lo
    t = (value - lo) / (hi - lo)
    return score_lo + max(0.0, min(1.0, t)) * (score_hi - score_lo)


def yield_subscore(
    spec_y: float | None,
    cf: float | None = None,
    *,
    lat: float | None = None,
    lon: float | None = None,
    country: str = "",
) -> int | None:
    """Map specific yield (kWh/kWp/yr) to 0–100 using regional ground-mount bands."""
    if spec_y is None:
        return None
    try:
        sy = float(spec_y)
    except (TypeError, ValueError):
        return None

    region = yield_region_key(lat=lat, lon=lon, country=country)
    poor, fair, good, excellent = yield_bands_for_region(region)

    if sy <= poor:
        score = _interp_band(sy, poor - 200, poor, 25, 45)
    elif sy <= fair:
        score = _interp_band(sy, poor, fair, 45, 60)
    elif sy <= good:
        score = _interp_band(sy, fair, good, 60, 78)
    elif sy <= excellent:
        score = _interp_band(sy, good, excellent, 78, 92)
    else:
        score = _interp_band(sy, excellent, excellent + 300, 92, 100)

    if cf is not None:
        try:
            cf_score = 40 + (float(cf) - 12) / 14 * 60
            score = 0.85 * score + 0.15 * max(0, min(100, cf_score))
        except (TypeError, ValueError):
            pass
    return max(0, min(100, round(score)))


def _confidence_stars(stars: int) -> str:
    filled = max(1, min(5, stars))
    return "★" * filled + "☆" * (5 - filled)


def assess_economic_viability(
    *,
    pvmath_score: int,
    verdict: str,
    components: Dict[str, int],
    score_mode: str,
    terrain_confirmed: bool = False,
    yield_available: bool = False,
    capacity_mwp: float | None = None,
) -> Dict[str, Any]:
    """Techno-economic presentation layer — complements the numeric score."""
    reg = int(components.get("regulatory", 70))
    terrain = int(components.get("terrain", 70))
    flood = int(components.get("flood", 70))

    confidence_pct = 42
    if terrain_confirmed:
        confidence_pct += 28
    if yield_available:
        confidence_pct += 22
    if score_mode == "full":
        confidence_pct += 5
    confidence_pct = min(95, confidence_pct)

    if confidence_pct >= 88:
        conf_label, conf_stars = "High Confidence", 5
    elif confidence_pct >= 72:
        conf_label, conf_stars = "Good Confidence", 4
    elif confidence_pct >= 55:
        conf_label, conf_stars = "Moderate Confidence", 3
    else:
        conf_label, conf_stars = "Screening Confidence", 2

    exec_weak = min(reg, terrain, flood)
    if pvmath_score < 45 or exec_weak < 35:
        investment_risk = "High"
    elif pvmath_score < 60 or exec_weak < 50:
        investment_risk = "Medium-High"
    elif pvmath_score < 70 or exec_weak < 60:
        investment_risk = "Medium"
    elif pvmath_score < 80:
        investment_risk = "Medium-Low"
    else:
        investment_risk = "Low"

    utility_mwp = capacity_mwp or 0.0
    if pvmath_score >= 70 and terrain >= 55 and utility_mwp >= 5:
        utility_rec = "YES"
    elif pvmath_score >= 55 and terrain >= 45:
        utility_rec = "CONDITIONAL"
    else:
        utility_rec = "NO"

    return {
        "engineering_confidence": conf_label,
        "engineering_confidence_pct": confidence_pct,
        "engineering_confidence_stars": _confidence_stars(conf_stars),
        "investment_risk": investment_risk,
        "utility_scale_recommended": utility_rec,
        "score_mode": score_mode,
        "qualitative_rating": verdict,
    }


def unified_pvmath_score(
    *,
    solar_score: int,
    terrain_score: int,
    flood_score: int,
    land_score: int,
    regulatory_score: int,
    yield_score: int | None = None,
    economic_score: int | None = None,
    terrain_confirmed: bool = False,
    capacity_mwp: float | None = None,
) -> dict:
    """Full PVMath score — terrain must come from TerrainIQ, not screening."""
    scores: Dict[str, int] = {
        "solar": solar_score,
        "terrain": terrain_score,
        "flood": flood_score,
        "land": land_score,
        "regulatory": regulatory_score,
    }
    include_yield = yield_score is not None
    if include_yield:
        scores["yield"] = yield_score
    include_economic = economic_score is not None
    if include_economic:
        scores["economic"] = economic_score

    weighted = calculate_pvmath_score(
        scores,
        include_yield=include_yield,
        include_economic=include_economic,
    )
    capped = min(weighted, terrain_score + _TERRAIN_CAP_MARGIN)
    overall = max(0, min(100, round(capped)))
    verdict = get_verdict_from_score(overall)
    score_mode = "full" if include_yield else "partial"

    viability = assess_economic_viability(
        pvmath_score=overall,
        verdict=verdict,
        components=scores,
        score_mode=score_mode,
        terrain_confirmed=terrain_confirmed,
        yield_available=include_yield,
        capacity_mwp=capacity_mwp,
    )

    return {
        "pvmath_score": overall,
        "verdict": verdict,
        "components": scores,
        "weighted_before_cap": round(weighted),
        "score_mode": score_mode,
        "viability": viability,
    }
