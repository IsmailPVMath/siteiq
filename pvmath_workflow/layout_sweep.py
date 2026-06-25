"""Layout configuration sweep — pitch/GCR matrix for Fixed Tilt and Tracker."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from layoutiq.bom import compute_bom
from layoutiq.engine import run_layout

FT_PORTRAITS = (1, 2, 3, 4)
SAT_PORTRAITS = (1, 2)
DEFAULT_PITCH_STEPS_M = (5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 9.0, 10.0, 11.0, 12.0)


def _row_ns_m(module_h: float, module_w: float, n_portrait: int, tracker: bool) -> float:
    return module_w * n_portrait if tracker else module_h * n_portrait


def _gcr(row_ns: float, pitch_m: float) -> float:
    if pitch_m <= 0:
        return 0.0
    return round(row_ns / pitch_m, 3)


def _pitch_candidates(row_ns: float, extra_pitches: Optional[List[float]] = None) -> List[float]:
    min_pitch = round(row_ns + 0.5, 2)
    seen = set()
    out: List[float] = []
    for p in [min_pitch] + list(extra_pitches or DEFAULT_PITCH_STEPS_M):
        val = round(float(p), 2)
        if val <= row_ns or val in seen:
            continue
        seen.add(val)
        out.append(val)
    return sorted(out)


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


def run_layout_sweep(
    boundary: Optional[List[List[float]]] = None,
    *,
    boundaries: Optional[List[List[List[float]]]] = None,
    module_h: float = 2.094,
    module_w: float = 1.038,
    module_wp: int = 550,
    setback_m: float = 5.0,
    azimuth: float = 180.0,
    pitch_steps_m: Optional[List[float]] = None,
    modules_per_string: int = 28,
    strings_per_inv: int = 4,
    inv_ac_kw: float = 100.0,
    include_bom: bool = False,
) -> Dict[str, Any]:
    """
    Iterate mount/portrait × pitch across one or more site parcels.

    Multiple parcels share a metric origin and their module counts/areas are
    summed per configuration. Returns a comparison table plus best row per config.
    """
    polys = _normalize_polys(boundary, boundaries)
    if not polys:
        return {"rows": [], "best_by_config": {}, "config_count": 0, "row_count": 0}

    ref_lat, ref_lon = _shared_ref(polys)
    table_rows: List[Dict[str, Any]] = []
    best_by_config: Dict[str, Dict[str, Any]] = {}

    for config_key, label, n_portrait, tracker in _config_specs():
        row_ns = _row_ns_m(module_h, module_w, n_portrait, tracker)
        mount_type = "sat" if tracker else "fixed_tilt"
        mount_label = "Single-Axis Tracker" if tracker else "Fixed Tilt"
        for pitch in _pitch_candidates(row_ns, pitch_steps_m):
            gcr = _gcr(row_ns, pitch)
            total_modules = 0
            total_rows = 0
            total_area_ha = 0.0
            for poly in polys:
                layout = run_layout(
                    poly,
                    module_h=module_h,
                    module_w=module_w,
                    n_portrait=n_portrait,
                    pitch=pitch,
                    setback=setback_m,
                    azimuth=azimuth,
                    mounting_type=mount_type,
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
                        "success": False,
                        "error": "No rows fit at this pitch",
                    }
                )
                continue

            dc_kwp = round(total_modules * module_wp / 1000, 1)
            total_area_ha = round(total_area_ha, 3)
            entry = {
                "config_key": config_key,
                "label": label,
                "mount_type": mount_label,
                "n_portrait": n_portrait,
                "pitch_m": pitch,
                "gcr": gcr,
                "success": True,
                "total_modules": total_modules,
                "total_rows": total_rows,
                "area_ha": total_area_ha,
                "dc_kwp": dc_kwp,
                "mw_per_ha": round(dc_kwp / total_area_ha, 3) if total_area_ha else None,
            }
            if include_bom and len(polys) == 1:
                single = run_layout(
                    polys[0],
                    module_h=module_h,
                    module_w=module_w,
                    n_portrait=n_portrait,
                    pitch=pitch,
                    setback=setback_m,
                    azimuth=azimuth,
                    mounting_type=mount_type,
                    ref_lat=ref_lat,
                    ref_lon=ref_lon,
                )
                if single:
                    entry["bom"] = compute_bom(
                        single,
                        module_wp,
                        n_portrait,
                        modules_per_string,
                        strings_per_inv,
                        inv_ac_kw,
                    )
            table_rows.append(entry)

            prev = best_by_config.get(config_key)
            if prev is None or (entry["dc_kwp"] > prev.get("dc_kwp", 0)):
                best_by_config[config_key] = entry

    return {
        "rows": table_rows,
        "best_by_config": best_by_config,
        "config_count": len(_config_specs()),
        "row_count": len(table_rows),
    }
