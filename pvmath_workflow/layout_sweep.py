"""Layout configuration sweep — pitch/GCR matrix for Fixed Tilt and Tracker."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from layoutiq.bom import compute_bom
from layoutiq.defaults import layout_params
from layoutiq.engine import run_layout
from pvmath_workflow.gcr_strategy import (
    FT_PORTRAITS,
    SAT_PORTRAITS,
    config_guidance,
    gcr_from_pitch,
    pitch_sweep_values,
    sweep_strategy_summary,
)

OptimizationMode = str
LandCost = str


def _row_ns_m(module_h: float, module_w: float, n_portrait: int, tracker: bool) -> float:
    # Chord (cross-row) dimension uses the module long edge for both fixed tilt
    # and SAT portrait mounting; n_portrait stacks modules across the chord.
    return module_h * n_portrait


def _config_specs() -> List[Tuple[str, str, int, bool]]:
    specs: List[Tuple[str, str, int, bool]] = []
    for n in FT_PORTRAITS:
        specs.append((f"FT_{n}P", f"Fixed Tilt — {n}P", n, False))
    for n in SAT_PORTRAITS:
        specs.append((f"SAT_{n}P", f"Single-Axis Tracker — {n}P", n, True))
    return specs


def _shared_ref(polys: List[List[List[float]]]) -> tuple:
    pts = [pt for poly in polys for pt in poly]
    ref_lat = sum(p[0] for p in pts) / len(pts)
    ref_lon = sum(p[1] for p in pts) / len(pts)
    return ref_lat, ref_lon


def _normalize_polys(
    boundary: Optional[List[List[float]]],
    boundaries: Optional[List[List[List[float]]]],
) -> List[List[List[float]]]:
    polys = [p for p in (boundaries or []) if p and len(p) >= 3]
    if not polys and boundary and len(boundary) >= 3:
        polys = [boundary]
    return polys


def _pick_recommended_row(
    rows: List[Dict[str, Any]],
    config_key: str,
    recommended_pitch: float,
) -> Optional[Dict[str, Any]]:
    """Row closest to the strategy-recommended pitch for this config."""
    candidates = [
        r for r in rows
        if r.get("config_key") == config_key and r.get("success")
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda r: abs(float(r.get("pitch_m", 0)) - recommended_pitch),
    )


def run_layout_sweep(
    boundary: Optional[List[List[float]]] = None,
    *,
    boundaries: Optional[List[List[List[float]]]] = None,
    restriction_polygons: Optional[List[List[List[float]]]] = None,
    tracker_restriction_polygons: Optional[List[List[List[float]]]] = None,
    module_h: float = 2.094,
    module_w: float = 1.038,
    module_wp: int = 550,
    setback_m: float = 5.0,
    azimuth: float = 180.0,
    pitch_steps_m: Optional[List[float]] = None,
    optimization_mode: OptimizationMode = "balanced",
    land_cost: LandCost = "auto",
    country: str = "",
    lat: Optional[float] = None,
    bifacial: bool = False,
    custom_gcr: Optional[float] = None,
    custom_pitch_m: Optional[float] = None,
    modules_per_string: int = 28,
    inter_string_gap_m: float = 0.5,
    tracker_string_options: Optional[List[int]] = None,
    max_tracker_length_m: float = 260.0,
    rows_per_block: int = 2,
    block_gap_m: float = 5.0,
    road_mode: str = "auto",
    road_preset: str = "sat_auto",
    strings_per_inv: int = 4,
    inv_ac_kw: float = 100.0,
    include_bom: bool = False,
) -> Dict[str, Any]:
    """
    Iterate mount/portrait × pitch across one or more site parcels.

    Pitch steps follow industry GCR bands (see gcr_strategy) for the selected
    optimization mode. Returns comparison rows, max-DC best per config, and
    strategy-recommended pitch per config.
    """
    polys = _normalize_polys(boundary, boundaries)
    restrictions = _normalize_polys(None, restriction_polygons)
    tracker_restrictions = _normalize_polys(None, tracker_restriction_polygons)
    if not polys:
        return {
            "rows": [],
            "best_by_config": {},
            "recommended_by_config": {},
            "gcr_guidance": {},
            "strategy": sweep_strategy_summary(
                mode=optimization_mode,
                land_cost=land_cost,
                country=country,
                lat=lat,
                bifacial=bifacial,
            ),
            "config_count": 0,
            "row_count": 0,
        }

    ref_lat, ref_lon = _shared_ref(polys)
    site_lat = lat if lat is not None else ref_lat

    lp = layout_params(
        module_h=module_h,
        module_w=module_w,
        module_wp=module_wp,
        modules_per_string=modules_per_string,
        inter_string_gap_m=inter_string_gap_m,
        tracker_string_options=tracker_string_options,
        max_tracker_length_m=max_tracker_length_m,
        rows_per_block=rows_per_block,
        block_gap_m=block_gap_m,
        road_mode=road_mode,  # type: ignore[arg-type]
        road_preset=road_preset,
    )

    table_rows: List[Dict[str, Any]] = []
    best_by_config: Dict[str, Dict[str, Any]] = {}
    gcr_guidance: Dict[str, Dict[str, Any]] = {}
    recommended_by_config: Dict[str, Dict[str, Any]] = {}

    for config_key, label, n_portrait, tracker in _config_specs():
        row_ns = _row_ns_m(module_h, module_w, n_portrait, tracker)
        mount_type = "sat" if tracker else "fixed_tilt"
        mount_label = "Single-Axis Tracker" if tracker else "Fixed Tilt"

        pitches, guidance = pitch_sweep_values(
            config_key,
            row_ns,
            mode=optimization_mode,
            land_cost=land_cost,
            country=country,
            lat=site_lat,
            bifacial=bifacial,
            custom_gcr=custom_gcr,
            custom_pitch_m=custom_pitch_m,
            extra_pitches=pitch_steps_m,
        )
        gcr_guidance[config_key] = guidance
        rec_pitch = float(guidance["recommended_pitch_m"])
        rec_gcr = float(guidance["recommended_gcr"])

        for pitch in pitches:
            gcr = gcr_from_pitch(row_ns, pitch)
            is_recommended = abs(pitch - rec_pitch) < 0.26
            active_restrictions = restrictions + (tracker_restrictions if tracker else [])

            total_modules = 0
            total_rows = 0
            total_area_ha = 0.0
            for poly in polys:
                layout = run_layout(
                    poly,
                    module_h=lp["module_h"],
                    module_w=lp["module_w"],
                    n_portrait=n_portrait,
                    pitch=pitch,
                    setback=setback_m,
                    azimuth=azimuth,
                    mounting_type=mount_type,
                    modules_per_string=lp["modules_per_string"],
                    inter_string_gap_m=lp["inter_string_gap_m"],
                    tracker_string_options=lp["tracker_string_options"],
                    max_tracker_length_m=lp["max_tracker_length_m"],
                    rows_per_block=lp["rows_per_block"],
                    block_gap_m=lp["block_gap_m"],
                    restriction_latlons=active_restrictions,
                    ref_lat=ref_lat,
                    ref_lon=ref_lon,
                )
                if layout:
                    total_modules += layout["total_modules"]
                    total_rows += layout["total_rows"]
                    total_area_ha += layout["area_ha"]

            if total_modules == 0:
                table_rows.append(
                    {
                        "config_key": config_key,
                        "label": label,
                        "mount_type": mount_label,
                        "n_portrait": n_portrait,
                        "pitch_m": pitch,
                        "gcr": gcr,
                        "is_recommended": is_recommended,
                        "success": False,
                        "error": "No rows fit at this pitch",
                    }
                )
                continue

            dc_kwp = round(total_modules * module_wp / 1000, 1)
            dc_mwp = round(dc_kwp / 1000, 3)
            total_area_ha = round(total_area_ha, 3)
            entry = {
                "config_key": config_key,
                "label": label,
                "mount_type": mount_label,
                "n_portrait": n_portrait,
                "pitch_m": pitch,
                "gcr": gcr,
                "is_recommended": is_recommended,
                "success": True,
                "total_modules": total_modules,
                "total_rows": total_rows,
                "area_ha": total_area_ha,
                "dc_kwp": dc_kwp,
                "dc_mwp": dc_mwp,
                "mw_per_ha": round(dc_mwp / total_area_ha, 3) if total_area_ha else None,
            }
            if include_bom and len(polys) == 1:
                single = run_layout(
                    polys[0],
                    module_h=lp["module_h"],
                    module_w=lp["module_w"],
                    n_portrait=n_portrait,
                    pitch=pitch,
                    setback=setback_m,
                    azimuth=azimuth,
                    mounting_type=mount_type,
                    modules_per_string=lp["modules_per_string"],
                    inter_string_gap_m=lp["inter_string_gap_m"],
                    tracker_string_options=lp["tracker_string_options"],
                    max_tracker_length_m=lp["max_tracker_length_m"],
                    rows_per_block=lp["rows_per_block"],
                    block_gap_m=lp["block_gap_m"],
                    restriction_latlons=active_restrictions,
                    ref_lat=ref_lat,
                    ref_lon=ref_lon,
                )
                if single:
                    entry["bom"] = compute_bom(
                        single,
                        module_wp,
                        n_portrait,
                        lp["modules_per_string"],
                        strings_per_inv,
                        inv_ac_kw,
                    )
            table_rows.append(entry)

            prev = best_by_config.get(config_key)
            if prev is None or (entry["dc_kwp"] > prev.get("dc_kwp", 0)):
                best_by_config[config_key] = entry

        rec_row = _pick_recommended_row(table_rows, config_key, rec_pitch)
        if rec_row:
            recommended_by_config[config_key] = rec_row
        else:
            # Fallback guidance row when no layout fits at recommended pitch
            recommended_by_config[config_key] = {
                "config_key": config_key,
                "label": label,
                "mount_type": mount_label,
                "n_portrait": n_portrait,
                "pitch_m": rec_pitch,
                "gcr": rec_gcr,
                "is_recommended": True,
                "success": False,
                "error": "Recommended pitch did not fit boundary",
            }

    return {
        "rows": table_rows,
        "best_by_config": best_by_config,
        "recommended_by_config": recommended_by_config,
        "gcr_guidance": gcr_guidance,
        "strategy": sweep_strategy_summary(
            mode=optimization_mode,
            land_cost=land_cost,
            country=country,
            lat=site_lat,
            bifacial=bifacial,
        ),
        "layout_params": lp,
        "config_count": len(_config_specs()),
        "row_count": len(table_rows),
    }
