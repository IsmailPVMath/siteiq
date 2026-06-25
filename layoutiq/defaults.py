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

# Default = equal pitch (no access-road gaps). Access roads are opt-in via presets;
# N-S road gaps intentionally widen pitch periodically when enabled.
DEFAULT_ROWS_PER_BLOCK = 0
DEFAULT_BLOCK_GAP_M = 0.0

ROAD_PRESETS: Dict[str, Dict[str, Any]] = {
    "sat_auto": {
        "label": "SAT auto — 2 rows + 5 m N-S gap",
        "rows_per_block": 2,
        "block_gap_m": 5.0,
        "road_mode": "auto",
    },
    "sat_wide": {
        "label": "Wide access — 2 rows + 8 m N-S gap",
        "rows_per_block": 2,
        "block_gap_m": 8.0,
        "road_mode": "manual",
    },
    "sat_single": {
        "label": "Single-row blocks — 1 row + 5 m gap",
        "rows_per_block": 1,
        "block_gap_m": 5.0,
        "road_mode": "manual",
    },
    "no_roads": {
        "label": "No access roads (strings only)",
        "rows_per_block": 0,
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
    road_mode: RoadMode = "off",
    road_preset: str = "no_roads",
) -> Dict[str, Any]:
    """Resolve road preset + mode into concrete engine parameters."""
    if road_mode == "auto":
        preset = ROAD_PRESETS["sat_auto"]
        return {
            "module_h": module_h,
            "module_w": module_w,
            "module_wp": module_wp,
            "modules_per_string": modules_per_string,
            "inter_string_gap_m": inter_string_gap_m,
            "tracker_string_options": tracker_string_options or DEFAULT_TRACKER_STRING_OPTIONS,
            "max_tracker_length_m": max_tracker_length_m,
            "rows_per_block": preset["rows_per_block"],
            "block_gap_m": preset["block_gap_m"],
            "road_mode": "auto",
            "road_preset": "sat_auto",
        }
    if road_mode == "manual" and road_preset in ROAD_PRESETS:
        preset = ROAD_PRESETS[road_preset]
        return {
            "module_h": module_h,
            "module_w": module_w,
            "module_wp": module_wp,
            "modules_per_string": modules_per_string,
            "inter_string_gap_m": inter_string_gap_m,
            "tracker_string_options": tracker_string_options or DEFAULT_TRACKER_STRING_OPTIONS,
            "max_tracker_length_m": max_tracker_length_m,
            "rows_per_block": preset["rows_per_block"],
            "block_gap_m": preset["block_gap_m"],
            "road_mode": "manual",
            "road_preset": road_preset,
        }
    if road_mode == "off":
        return {
            "module_h": module_h,
            "module_w": module_w,
            "module_wp": module_wp,
            "modules_per_string": modules_per_string,
            "inter_string_gap_m": inter_string_gap_m,
            "tracker_string_options": tracker_string_options or DEFAULT_TRACKER_STRING_OPTIONS,
            "max_tracker_length_m": max_tracker_length_m,
            "rows_per_block": 0,
            "block_gap_m": 0.0,
            "road_mode": "off",
            "road_preset": "no_roads",
        }
    # manual custom values from caller
    return {
        "module_h": module_h,
        "module_w": module_w,
        "module_wp": module_wp,
        "modules_per_string": modules_per_string,
        "inter_string_gap_m": inter_string_gap_m,
        "tracker_string_options": tracker_string_options or DEFAULT_TRACKER_STRING_OPTIONS,
        "max_tracker_length_m": max_tracker_length_m,
        "rows_per_block": max(0, rows_per_block),
        "block_gap_m": max(0.0, block_gap_m),
        "road_mode": road_mode,
        "road_preset": road_preset or "custom",
    }
