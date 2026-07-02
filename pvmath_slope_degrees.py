"""Slope display helpers — store as % grade internally, show as degrees in UI/PDF."""

from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Tuple

# Slope class bands for TerrainIQ maps and tables (degrees).
SLOPE_DEG_BANDS: Tuple[Tuple[float, float, str, str], ...] = (
    (0.0, 2.5, "#14532d", "0 – 2.5° (excellent)"),
    (2.5, 5.0, "#1b8a3a", "2.5 – 5° (good)"),
    (5.0, 7.5, "#eab308", "5 – 7.5° (acceptable)"),
    (7.5, 10.0, "#f97316", "7.5 – 10° (challenging)"),
    (10.0, 20.0, "#d0021b", "10 – 20° (critical)"),
)


def slope_pct_to_deg(pct: float | None) -> float | None:
    if pct is None:
        return None
    try:
        return math.degrees(math.atan(float(pct) / 100.0))
    except (TypeError, ValueError):
        return None


def slope_deg_bins(slopes_pct: Iterable[float]) -> List[float]:
    """Return area % in each degree band (5 bins, sums to ~100)."""
    valid_deg = [d for d in (slope_pct_to_deg(s) for s in slopes_pct) if d is not None]
    n = len(valid_deg)
    if n == 0:
        return [0.0, 0.0, 0.0, 0.0, 0.0]
    counts = [
        sum(1 for d in valid_deg if d <= 2.5),
        sum(1 for d in valid_deg if 2.5 < d <= 5),
        sum(1 for d in valid_deg if 5 < d <= 7.5),
        sum(1 for d in valid_deg if 7.5 < d <= 10),
        sum(1 for d in valid_deg if d > 10),
    ]
    return [round(100.0 * c / n, 1) for c in counts]


def pct_area_over_deg(slopes_pct: Iterable[float], threshold_deg: float) -> float:
    deg = [slope_pct_to_deg(s) for s in slopes_pct if s is not None and s == s]
    valid = [d for d in deg if d is not None]
    if not valid:
        return 0.0
    return round(100.0 * sum(1 for d in valid if d > threshold_deg) / len(valid), 1)


def slope_color_hex_deg(deg: float) -> str:
    for lo, hi, color, _ in SLOPE_DEG_BANDS:
        if deg <= hi:
            return color
    return SLOPE_DEG_BANDS[-1][2]
