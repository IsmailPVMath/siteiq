"""Fixed-tilt layout matrix (1P–4P portrait) + BOM for unified workflow."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from layoutiq.bom import compute_bom
from layoutiq.engine import run_layout
from pvmath_workflow.gcr_strategy import config_key_for, pitch_from_gcr, recommended_gcr

FT_PORTRAITS = (1, 2, 3, 4)


def _default_pitch_m(
    module_h: float,
    module_w: float,
    n_portrait: int,
    pitch_m: Optional[float],
    *,
    lat: Optional[float] = None,
    country: str = "",
) -> float:
    if pitch_m and pitch_m > 0:
        return float(pitch_m)
    row_ns = module_h * n_portrait
    key = config_key_for(n_portrait, tracker=False)
    gcr = recommended_gcr(key, mode="balanced", country=country, lat=lat)
    return pitch_from_gcr(row_ns, gcr)


def run_fixed_tilt_layout_matrix(
    boundary: List[List[float]],
    *,
    module_h: float = 2.094,
    module_w: float = 1.038,
    module_wp: int = 550,
    pitch_m: Optional[float] = None,
    setback_m: float = 5.0,
    azimuth: float = 180.0,
    modules_per_string: int = 28,
    strings_per_inv: int = 4,
    inv_ac_kw: float = 100.0,
) -> List[Dict[str, Any]]:
    """
  Run layout + BOM for Fixed Tilt 1P–4P portrait on one boundary.

  boundary: [[lat, lon], ...]
  """
    if not boundary or len(boundary) < 3:
        return []

    results: List[Dict[str, Any]] = []
    for n in FT_PORTRAITS:
        pitch = _default_pitch_m(module_h, module_w, n, pitch_m)
        row_ns = module_h * n
        if pitch <= row_ns:
            pitch = round(row_ns + 0.5, 1)

        layout = run_layout(
            boundary,
            module_h=module_h,
            module_w=module_w,
            n_portrait=n,
            pitch=pitch,
            setback=setback_m,
            azimuth=azimuth,
            mounting_type="fixed_tilt",
        )
        if not layout:
            results.append({
                "config_key": f"FT_{n}P",
                "label": f"Fixed Tilt — {n} portrait ({n}P)",
                "n_portrait": n,
                "pitch_m": pitch,
                "success": False,
                "error": "Layout failed — boundary too small after setback or pitch too large",
            })
            continue

        bom = compute_bom(
            layout,
            module_wp,
            n,
            modules_per_string,
            strings_per_inv,
            inv_ac_kw,
        )
        dc_kwp = round(layout["total_modules"] * module_wp / 1000, 1)
        results.append({
            "config_key": f"FT_{n}P",
            "label": f"Fixed Tilt — {n} portrait ({n}P)",
            "n_portrait": n,
            "pitch_m": pitch,
            "success": True,
            "layout": {
                "total_modules": layout["total_modules"],
                "total_rows": layout["total_rows"],
                "area_ha": layout["area_ha"],
                "dc_kwp": dc_kwp,
                "mw_per_ha": round(dc_kwp / layout["area_ha"], 3) if layout["area_ha"] else None,
            },
            "bom": bom,
        })
    return results
