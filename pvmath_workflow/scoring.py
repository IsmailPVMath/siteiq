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


def unified_pvmath_score(
    *,
    solar_score: int,
    terrain_score: int,
    flood_score: int,
    land_score: int,
    regulatory_score: int,
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
    # Terrain binds on challenging sites — excellent solar cannot mask poor terrain.
    capped = min(weighted, terrain_score + 15)
    overall = max(0, min(100, capped))
    return {
        "pvmath_score": overall,
        "verdict": get_verdict_from_score(overall),
        "components": scores,
        "weighted_before_cap": weighted,
    }
