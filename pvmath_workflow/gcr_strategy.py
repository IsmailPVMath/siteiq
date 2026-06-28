"""Industry-aligned GCR / pitch strategy for LayoutIQ conceptual sweeps.

Defaults follow utility-scale EPC practice and PVsyst-style backtracking assumptions.
Optimization modes shift within documented typical ranges; land-cost and latitude
apply secondary tuning — not a substitute for full PVsyst shading studies.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional, Tuple

OptimizationMode = Literal["high_energy", "balanced", "land_optimized", "custom"]
LandCost = Literal["auto", "cheap", "balanced", "expensive"]

FT_PORTRAITS = (1, 2, 3, 4)
SAT_PORTRAITS = (1, 2)

# Per mount/portrait: balanced default GCR, typical GCR band, practical pitch band (m),
# and land-cost anchor bands (midpoints used for high-energy / land-optimized modes).
_CONFIG_TABLE: Dict[str, Dict[str, Any]] = {
    "FT_1P": {
        "default_gcr": 0.45,
        "gcr_typical": (0.38, 0.52),
        "pitch_m": (4.0, 6.5),
        "gcr_cheap": (0.38, 0.45),
        "gcr_expensive": (0.55, 0.65),
    },
    "FT_2P": {
        "default_gcr": 0.47,
        "gcr_typical": (0.40, 0.55),
        "pitch_m": (5.5, 8.5),
        "gcr_cheap": (0.38, 0.45),
        "gcr_expensive": (0.55, 0.65),
    },
    "FT_3P": {
        "default_gcr": 0.50,
        "gcr_typical": (0.42, 0.58),
        "pitch_m": (7.0, 10.0),
        "gcr_cheap": (0.38, 0.45),
        "gcr_expensive": (0.55, 0.65),
    },
    "FT_4P": {
        "default_gcr": 0.52,
        "gcr_typical": (0.45, 0.60),
        "pitch_m": (8.5, 12.0),
        "gcr_cheap": (0.38, 0.45),
        "gcr_expensive": (0.55, 0.65),
    },
    "SAT_1P": {
        "default_gcr": 0.33,
        "gcr_typical": (0.28, 0.38),
        "pitch_m": (6.0, 9.0),
        "gcr_cheap": (0.28, 0.33),
        "gcr_expensive": (0.38, 0.42),
    },
    "SAT_2P": {
        "default_gcr": 0.35,
        "gcr_typical": (0.30, 0.40),
        "pitch_m": (7.0, 10.0),
        "gcr_cheap": (0.28, 0.33),
        "gcr_expensive": (0.38, 0.42),
    },
}

_EXPENSIVE_LAND = frozenset(
    {
        "japan",
        "jp",
        "netherlands",
        "nl",
        "germany",
        "de",
        "korea",
        "south korea",
        "republic of korea",
        "kr",
        "switzerland",
        "ch",
        "austria",
        "at",
        "belgium",
        "be",
        "luxembourg",
        "lu",
        "singapore",
        "sg",
        "israel",
        "il",
        "united kingdom",
        "uk",
        "great britain",
        "england",
    }
)

_CHEAP_LAND = frozenset(
    {
        "texas",
        "saudi arabia",
        "saudi",
        "ksa",
        "australia",
        "au",
        "chile",
        "cl",
        "india",
        "in",
        "rajasthan",
        "egypt",
        "eg",
        "morocco",
        "ma",
        "mexico",
        "mx",
        "brazil",
        "br",
        "argentina",
        "ar",
        "south africa",
        "za",
        "namibia",
        "na",
        "kazakhstan",
        "kz",
        "united states",
        "usa",
        "us",
    }
)


def config_key_for(n_portrait: int, tracker: bool) -> str:
    prefix = "SAT" if tracker else "FT"
    return f"{prefix}_{n_portrait}P"


def all_config_keys() -> List[str]:
    keys = [config_key_for(n, False) for n in FT_PORTRAITS]
    keys.extend(config_key_for(n, True) for n in SAT_PORTRAITS)
    return keys


def _norm_country(country: str) -> str:
    return re.sub(r"\s+", " ", (country or "").strip().lower())


def infer_land_cost(country: str, lat: float | None = None) -> LandCost:
    """Infer land-cost class from country name (and coarse latitude fallback)."""
    c = _norm_country(country)
    if c:
        for token in re.split(r"[,;/]", c):
            token = token.strip()
            if token in _EXPENSIVE_LAND:
                return "expensive"
            if token in _CHEAP_LAND:
                return "cheap"
        if any(token in c for token in _EXPENSIVE_LAND):
            return "expensive"
        if any(token in c for token in _CHEAP_LAND):
            return "cheap"
    # Very coarse latitude heuristic when country unknown
    if lat is not None and abs(lat) < 28:
        return "cheap"
    return "balanced"


def resolve_land_cost(
    land_cost: LandCost,
    country: str = "",
    lat: float | None = None,
) -> Literal["cheap", "balanced", "expensive"]:
    if land_cost == "auto":
        return infer_land_cost(country, lat)
    return land_cost


def _clamp_gcr(value: float, config_key: str) -> float:
    spec = _CONFIG_TABLE[config_key]
    lo = min(spec["gcr_typical"][0], spec["gcr_cheap"][0]) * 0.9
    hi = max(spec["gcr_typical"][1], spec["gcr_expensive"][1]) * 1.02
    return round(max(lo, min(hi, value)), 3)


def recommended_gcr(
    config_key: str,
    *,
    mode: OptimizationMode = "balanced",
    land_cost: LandCost = "auto",
    country: str = "",
    lat: float | None = None,
    bifacial: bool = False,
    custom_gcr: float | None = None,
) -> float:
    """Return target GCR for a configuration under the chosen optimization mode."""
    spec = _CONFIG_TABLE[config_key]
    resolved_land = resolve_land_cost(land_cost, country, lat)

    if mode == "custom" and custom_gcr is not None and custom_gcr > 0:
        return _clamp_gcr(float(custom_gcr), config_key)

    if mode == "balanced":
        gcr = float(spec["default_gcr"])
    elif mode == "high_energy":
        if resolved_land == "cheap":
            gcr = sum(spec["gcr_cheap"]) / 2.0
        else:
            gcr = spec["gcr_typical"][0] + 0.01
    elif mode == "land_optimized":
        if resolved_land == "expensive":
            gcr = sum(spec["gcr_expensive"]) / 2.0
        else:
            gcr = spec["gcr_typical"][1] - 0.01
    else:
        gcr = float(spec["default_gcr"])

    # Latitude tuning (subtle — conceptual screening only)
    if lat is not None:
        abs_lat = abs(lat)
        if abs_lat < 25:
            if mode == "land_optimized":
                gcr += 0.015
            elif mode == "high_energy":
                gcr -= 0.02
        elif abs_lat > 45:
            if mode != "land_optimized":
                gcr -= 0.02
            else:
                gcr -= 0.01

    if bifacial and mode in ("balanced", "high_energy"):
        gcr -= 0.03

    return _clamp_gcr(gcr, config_key)


def pitch_from_gcr(row_ns_m: float, gcr: float) -> float:
    if gcr <= 0:
        return round(row_ns_m + 0.5, 2)
    return round(row_ns_m / gcr, 2)


def gcr_from_pitch(row_ns_m: float, pitch_m: float) -> float:
    if pitch_m <= 0:
        return 0.0
    return round(row_ns_m / pitch_m, 3)


def config_guidance(
    config_key: str,
    row_ns_m: float,
    *,
    mode: OptimizationMode = "balanced",
    land_cost: LandCost = "auto",
    country: str = "",
    lat: float | None = None,
    bifacial: bool = False,
    custom_gcr: float | None = None,
    custom_pitch_m: float | None = None,
) -> Dict[str, Any]:
    """Per-configuration recommendation metadata for API / UI."""
    spec = _CONFIG_TABLE[config_key]
    resolved_land = resolve_land_cost(land_cost, country, lat)
    rec_gcr = recommended_gcr(
        config_key,
        mode=mode,
        land_cost=land_cost,
        country=country,
        lat=lat,
        bifacial=bifacial,
        custom_gcr=custom_gcr,
    )
    rec_pitch = (
        round(float(custom_pitch_m), 2)
        if custom_pitch_m and custom_pitch_m > row_ns_m
        else pitch_from_gcr(row_ns_m, rec_gcr)
    )
    rec_gcr = gcr_from_pitch(row_ns_m, rec_pitch)

    return {
        "config_key": config_key,
        "recommended_gcr": rec_gcr,
        "recommended_pitch_m": rec_pitch,
        "gcr_typical_min": spec["gcr_typical"][0],
        "gcr_typical_max": spec["gcr_typical"][1],
        "pitch_m_min": spec["pitch_m"][0],
        "pitch_m_max": spec["pitch_m"][1],
        "balanced_default_gcr": spec["default_gcr"],
        "land_cost": resolved_land,
    }


def pitch_sweep_values(
    config_key: str,
    row_ns_m: float,
    *,
    mode: OptimizationMode = "balanced",
    land_cost: LandCost = "auto",
    country: str = "",
    lat: float | None = None,
    bifacial: bool = False,
    custom_gcr: float | None = None,
    custom_pitch_m: float | None = None,
    extra_pitches: Optional[List[float]] = None,
    gcr_step: float = 0.03,
) -> Tuple[List[float], Dict[str, Any]]:
    """
    Build ordered pitch list for a configuration sweep.

    The sweep is GCR-driven: we step across the realistic GCR band and convert
    to pitch via the chord, so displayed GCRs stay in industry range for any
    chord (1P vs 2P, fixed vs tracker). Returns (pitches, guidance_dict).
    """
    spec = _CONFIG_TABLE[config_key]
    guidance = config_guidance(
        config_key,
        row_ns_m,
        mode=mode,
        land_cost=land_cost,
        country=country,
        lat=lat,
        bifacial=bifacial,
        custom_gcr=custom_gcr,
        custom_pitch_m=custom_pitch_m,
    )
    rec_pitch = guidance["recommended_pitch_m"]

    if custom_pitch_m and custom_pitch_m > row_ns_m:
        return [round(float(custom_pitch_m), 2)], guidance

    candidates: List[float] = []

    if mode == "custom" and custom_gcr and custom_gcr > 0:
        base = pitch_from_gcr(row_ns_m, float(custom_gcr))
        for scale in (0.92, 0.96, 1.0, 1.04, 1.08):
            candidates.append(round(base * scale, 2))
    else:
        gcr_lo = min(spec["gcr_typical"][0], spec["gcr_cheap"][0])
        gcr_hi = max(spec["gcr_typical"][1], spec["gcr_expensive"][1])
        g = gcr_lo
        while g <= gcr_hi + 1e-9:
            candidates.append(pitch_from_gcr(row_ns_m, round(g, 3)))
            g += gcr_step

    candidates.append(rec_pitch)
    if extra_pitches:
        candidates.extend(float(p) for p in extra_pitches)

    seen = set()
    out: List[float] = []
    for val in sorted(candidates):
        v = round(float(val), 2)
        if v <= row_ns_m or v in seen:
            continue
        seen.add(v)
        out.append(v)
    if not out:
        out = [max(rec_pitch, row_ns_m + 0.5)]
    return out, guidance


def sweep_strategy_summary(
    *,
    mode: OptimizationMode,
    land_cost: LandCost,
    country: str,
    lat: float | None,
    bifacial: bool,
) -> Dict[str, Any]:
    resolved = resolve_land_cost(land_cost, country, lat)
    mode_labels = {
        "high_energy": "High energy — wider row spacing, lower GCR, higher yield",
        "balanced": "Balanced — industry default GCR per mount/portrait",
        "land_optimized": "Land optimized — tighter spacing, higher GCR, more MW/ha",
        "custom": "Custom — user-defined GCR or pitch",
    }
    land_labels = {
        "cheap": "Low land cost — favour wider spacing (high-energy band)",
        "balanced": "Moderate land cost",
        "expensive": "High land cost — favour tighter spacing (land-optimized band)",
    }
    return {
        "optimization_mode": mode,
        "land_cost_input": land_cost,
        "land_cost_resolved": resolved,
        "country": country,
        "latitude": lat,
        "bifacial": bifacial,
        "mode_label": mode_labels.get(mode, mode),
        "land_cost_label": land_labels.get(resolved, resolved),
        "note": (
            "Conceptual layout bands aligned with utility-scale practice. "
            "Confirm shading and energy with PVsyst or detailed design."
        ),
    }
