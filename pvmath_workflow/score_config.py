"""PVMath composite score weights and regional yield bands (Jun 2026)."""

from __future__ import annotations

from typing import Dict, List, Tuple

# Full composite — all six factors (YieldIQ run).
PVMATH_WEIGHTS_FULL: Dict[str, float] = {
    "regulatory": 0.22,
    "terrain": 0.22,
    "yield": 0.18,
    "land": 0.15,
    "flood": 0.15,
    "solar": 0.08,
}

# Partial composite — YieldIQ pending; yield weight redistributed (+8% reg, +10% terrain).
PVMATH_WEIGHTS_PARTIAL: Dict[str, float] = {
    "regulatory": 0.30,
    "terrain": 0.32,
    "land": 0.15,
    "flood": 0.15,
    "solar": 0.08,
}

# Display labels for PDF / UI breakdown tables.
SUITABILITY_WEIGHTS: Tuple[Tuple[str, str, int], ...] = (
    ("Grid / Regulatory", "regulatory", 22),
    ("Terrain", "terrain", 22),
    ("Energy Yield", "yield", 18),
    ("Land Use", "land", 15),
    ("Flood Risk", "flood", 15),
    ("Solar Resource", "solar", 8),
)

SUITABILITY_WEIGHTS_PARTIAL: Tuple[Tuple[str, str, int], ...] = (
    ("Grid / Regulatory", "regulatory", 30),
    ("Terrain", "terrain", 32),
    ("Land Use", "land", 15),
    ("Flood Risk", "flood", 15),
    ("Solar Resource", "solar", 8),
)

# Regional ground-mount specific-yield bands (kWh/kWp/yr): poor, fair, good, excellent.
_YIELD_BANDS: Dict[str, Tuple[float, float, float, float]] = {
    "eu_central": (950, 1100, 1250, 1450),
    "eu_south": (1100, 1250, 1450, 1700),
    "us_southwest": (1400, 1650, 1850, 2200),
    "us_other": (1100, 1250, 1450, 1700),
    "india": (1300, 1500, 1700, 1950),
    "australia": (1350, 1550, 1750, 2000),
    "global": (1000, 1150, 1350, 1600),
}

_EU_CENTRAL = (
    "germany", "deutschland", "austria", "österreich", "poland", "polska",
    "czech", "slovak", "hungary", "switzerland", "schweiz", "netherlands",
    "belgium", "denmark", "sweden", "norway",
)
_EU_SOUTH = ("spain", "españa", "italy", "italia", "portugal", "greece", "france", "croatia")
_US_SW = ("arizona", "nevada", "california", "texas", "new mexico", "utah", "colorado")


def yield_region_key(*, lat: float | None = None, lon: float | None = None, country: str = "") -> str:
    """Best-effort climate band for regional yield scoring."""
    c = (country or "").lower()
    if any(x in c for x in _EU_CENTRAL):
        return "eu_central"
    if any(x in c for x in _EU_SOUTH):
        return "eu_south"
    if "india" in c:
        return "india"
    if "australia" in c:
        return "australia"
    if any(x in c for x in ("united states", "usa", "america")):
        if lat is not None and lon is not None and 25 <= lat <= 42 and -125 <= lon <= -100:
            return "us_southwest"
        return "us_other"
    if lat is not None and lon is not None:
        if 34 <= lat <= 72 and -25 <= lon <= 45:
            return "eu_south" if lat < 44 else "eu_central"
        if 8 <= lat <= 35 and 68 <= lon <= 97:
            return "india"
        if -45 <= lat <= -10 and 110 <= lon <= 155:
            return "australia"
        if 25 <= lat <= 50 and -125 <= lon <= -65:
            return "us_southwest" if lat <= 42 and lon <= -100 else "us_other"
    return "global"


def yield_bands_for_region(region: str) -> Tuple[float, float, float, float]:
    return _YIELD_BANDS.get(region, _YIELD_BANDS["global"])


def calculate_pvmath_score(scores: dict, *, include_yield: bool = False) -> int:
    """Weighted composite from factor scores (0–100 each)."""
    weights = PVMATH_WEIGHTS_FULL if include_yield else PVMATH_WEIGHTS_PARTIAL
    raw = 0.0
    for key, weight in weights.items():
        raw += float(scores.get(key, 0)) * weight
    return max(0, min(100, round(raw)))


def get_verdict_from_score(score: int) -> str:
    """PVMath verdict label from overall score."""
    s = int(score)
    if s >= 90:
        return "EXCELLENT"
    if s >= 80:
        return "VERY GOOD"
    if s >= 70:
        return "GOOD"
    if s >= 60:
        return "ACCEPTABLE"
    if s >= 45:
        return "CHALLENGING"
    return "CRITICAL"
