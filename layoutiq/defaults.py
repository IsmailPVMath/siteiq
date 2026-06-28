"""Default module and access-road parameters for LayoutIQ."""

from __future__ import annotations

from typing import Any, Dict, Literal

RoadMode = Literal["auto", "manual", "off"]

# Standard 550 Wp bifacial-style module (2.094 × 1.038 m)
DEFAULT_MODULE_H = 2.094
DEFAULT_MODULE_W = 1.038
DEFAULT_MODULE_WP = 550
DEFAULT_MODULES_PER_STRING = 28
DEFAULT_INTER_STRING_GAP_M = 0.5
DEFAULT_TRACKER_STRING_OPTIONS = [8, 7, 6, 5]
DEFAULT_MAX_TRACKER_LENGTH_M = 260.0

# Default = equal pitch (no access-road gaps). Access roads are opt-in via presets.
DEFAULT_ROWS_PER_BLOCK = 0
DEFAULT_BLOCK_GAP_M = 0.0
DEFAULT_NS_GAP_1_M = 0.0
DEFAULT_COLS_PER_BLOCK = 0
DEFAULT_EW_GAP_M = 0.0

# PVCase-style roads: constant pitch, E-W gap after N columns, N-S gaps at north block end.
ROAD_PRESETS: Dict[str, Dict[str, Any]] = {
    "sat_auto": {
        "label": "50 columns → 6 m E-W gap · 16 bands → 0.6 + 5 m N-S",
        "cols_per_block": 50,
        "ew_gap_m": 6.0,
        "rows_per_block": 16,
        "ns_gap_1_m": 0.6,
        "block_gap_m": 5.0,
        "road_mode": "auto",
    },
    "sat_ew_100": {
        "label": "100 columns → 6 m E-W gap · 16 bands → 0.6 + 5 m N-S",
        "cols_per_block": 100,
        "ew_gap_m": 6.0,
        "rows_per_block": 16,
        "ns_gap_1_m": 0.6,
        "block_gap_m": 5.0,
        "road_mode": "manual",
    },
    "sat_wide": {
        "label": "50 columns → 8 m E-W gap · 16 bands → 0.6 + 8 m N-S",
        "cols_per_block": 50,
        "ew_gap_m": 8.0,
        "rows_per_block": 16,
        "ns_gap_1_m": 0.6,
        "block_gap_m": 8.0,
        "road_mode": "manual",
    },
    "no_roads": {
        "label": "No access roads (constant pitch)",
        "cols_per_block": 0,
        "ew_gap_m": 0.0,
        "rows_per_block": 0,
        "ns_gap_1_m": 0.0,
        "block_gap_m": 0.0,
        "road_mode": "off",
    },
}


def layout_params(
    *,
    module_h: float = DEFAULT_MODULE_H,
    module_w: float = DEFAULT_MODULE_W,
    module_wp: int = DEFAULT_MODULE_WP,
    modules_per_string: int = DEFAULT_MODULES_PER_STRING,
    inter_string_gap_m: float = DEFAULT_INTER_STRING_GAP_M,
    tracker_string_options: list[int] | None = None,
    max_tracker_length_m: float = DEFAULT_MAX_TRACKER_LENGTH_M,
    rows_per_block: int = DEFAULT_ROWS_PER_BLOCK,
    block_gap_m: float = DEFAULT_BLOCK_GAP_M,
    ns_gap_1_m: float = DEFAULT_NS_GAP_1_M,
    cols_per_block: int = DEFAULT_COLS_PER_BLOCK,
    ew_gap_m: float = DEFAULT_EW_GAP_M,
    road_mode: RoadMode = "off",
    road_preset: str = "no_roads",
) -> Dict[str, Any]:
    """Resolve road preset + mode into concrete engine parameters."""
    base = {
        "module_h": module_h,
        "module_w": module_w,
        "module_wp": module_wp,
        "modules_per_string": modules_per_string,
        "inter_string_gap_m": inter_string_gap_m,
        "tracker_string_options": tracker_string_options or DEFAULT_TRACKER_STRING_OPTIONS,
        "max_tracker_length_m": max_tracker_length_m,
    }
    if road_mode == "auto":
        preset = ROAD_PRESETS["sat_auto"]
        return {
            **base,
            "rows_per_block": preset["rows_per_block"],
            "block_gap_m": preset["block_gap_m"],
            "ns_gap_1_m": preset["ns_gap_1_m"],
            "cols_per_block": preset["cols_per_block"],
            "ew_gap_m": preset["ew_gap_m"],
            "road_mode": "auto",
            "road_preset": "sat_auto",
        }
    if road_mode == "manual" and road_preset in ROAD_PRESETS:
        preset = ROAD_PRESETS[road_preset]
        return {
            **base,
            "rows_per_block": preset.get("rows_per_block", 0),
            "block_gap_m": preset.get("block_gap_m", 0.0),
            "ns_gap_1_m": preset.get("ns_gap_1_m", 0.0),
            "cols_per_block": preset.get("cols_per_block", 0),
            "ew_gap_m": preset.get("ew_gap_m", 0.0),
            "road_mode": "manual",
            "road_preset": road_preset,
        }
    if road_mode == "off":
        return {
            **base,
            "rows_per_block": 0,
            "block_gap_m": 0.0,
            "ns_gap_1_m": 0.0,
            "cols_per_block": 0,
            "ew_gap_m": 0.0,
            "road_mode": "off",
            "road_preset": "no_roads",
        }
    # manual custom values from caller
    return {
        **base,
        "rows_per_block": max(0, rows_per_block),
        "block_gap_m": max(0.0, block_gap_m),
        "ns_gap_1_m": max(0.0, ns_gap_1_m),
        "cols_per_block": max(0, cols_per_block),
        "ew_gap_m": max(0.0, ew_gap_m),
        "road_mode": road_mode,
        "road_preset": road_preset or "custom",
    }
