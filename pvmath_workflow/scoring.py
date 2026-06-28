"""PVMath score helpers for the unified React workflow."""

from __future__ import annotations

from pvmath_screening_library import calculate_pvmath_score, get_verdict_from_score

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


def tier_score(label: str) -> int:
    key = (label or "").lower().split()[0]
    for k, v in _TIER_SCORE.items():
        if k in key:
            return v
    return 55


def yield_subscore(spec_y: float | None, cf: float | None = None) -> int | None:
    """Map a config's specific yield (kWh/kWp/yr) to a 0-100 energy-yield score.

    Anchored to global ground-mount norms: ~1000 poor → ~2200+ excellent.
    Capacity factor nudges the result when available.
    """
    if spec_y is None:
        return None
    try:
        sy = float(spec_y)
    except (TypeError, ValueError):
        return None
    score = 40 + (sy - 1000) / 1200 * 60  # 1000→40, 2200→100
    if cf is not None:
        try:
            score = 0.85 * score + 0.15 * (40 + (float(cf) - 12) / 14 * 60)  # CF 12→40, 26→100
        except (TypeError, ValueError):
            pass
    return max(0, min(100, round(score)))


def unified_pvmath_score(
    *,
    solar_score: int,
    terrain_score: int,
    flood_score: int,
    land_score: int,
    regulatory_score: int,
    yield_score: int | None = None,
) -> dict:
    """Full PVMath score — terrain must come from TerrainIQ, not screening."""
    scores = {
        "solar": solar_score,
        "terrain": terrain_score,
        "flood": flood_score,
        "land": land_score,
        "regulatory": regulatory_score,
    }
    weighted = calculate_pvmath_score(scores)
    # Energy yield, when available, refines the screening composite (15% weight).
    if yield_score is not None:
        weighted = 0.85 * weighted + 0.15 * yield_score
        scores["yield"] = yield_score
    # Terrain binds on challenging sites — excellent solar cannot mask poor terrain.
    capped = min(weighted, terrain_score + 15)
    overall = max(0, min(100, round(capped)))
    return {
        "pvmath_score": overall,
        "verdict": get_verdict_from_score(overall),
        "components": scores,
        "weighted_before_cap": round(weighted),
    }
