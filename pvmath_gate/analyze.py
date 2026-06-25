"""Orchestrate one gate analysis run (solar + terrain + yield + layout + BOM)."""

from __future__ import annotations

from pvmath_capacity import format_mwp_range, format_mwh_range, screening_capacity
from pvmath_screening_library import calculate_pvmath_score, get_verdict_from_score
from pvmath_yield import get_solar_data, run_all_configs
from layoutiq.bom import compute_bom
from layoutiq.engine import run_layout
from pvmath_gate.models import GateRequest, GateResponse
from pvmath_gate.screening import (
    assess_regulatory,
    assess_slope,
    assess_solar,
    get_flood_risk,
    get_terrain_data,
)

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


def _tier_score(label: str) -> int:
    key = (label or "").lower().split()[0]
    for k, v in _TIER_SCORE.items():
        if k in key:
            return v
    return 55


def run_gate_analysis(req: GateRequest) -> GateResponse:
    errors: list[str] = []
    mount = req.mount_type
    mounting_type = "sat" if mount == "Single-Axis Tracker" else "fixed_tilt"
    polygons = [req.boundary] if req.boundary and len(req.boundary) >= 3 else None

    # ── Solar (SiteIQ engine) ─────────────────────────────────────────────
    solar = get_solar_data(req.lat, req.lon, mount_type=mount)
    if not solar.get("success"):
        errors.append(solar.get("error", "Solar data unavailable"))

    solar_label, solar_detail = ("—", "—")
    if solar.get("success"):
        solar_label, solar_detail = assess_solar(float(solar["annual_ghi"]))

    # ── Terrain ───────────────────────────────────────────────────────────
    terrain = get_terrain_data(
        req.lat, req.lon,
        polygons=polygons,
    )
    if not terrain.get("success"):
        errors.append(terrain.get("error", "Terrain data unavailable"))

    slope_label, slope_detail = ("—", "—")
    slope_pct = None
    if terrain.get("success"):
        slope_pct = terrain.get("max_slope_pct")
        slope_label, slope_detail = assess_slope(float(slope_pct), mount)

    flood = get_flood_risk(
        req.lat, req.lon,
        terrain.get("center_elev") if terrain.get("success") else None,
    )
    regulatory = assess_regulatory(req.lat, req.lon, req.land_use, req.country)

    # ── Capacity (screening band) ─────────────────────────────────────────
    yield_kwh = solar.get("annual_yield") if solar.get("success") else None
    cap = screening_capacity(req.area_ha, req.land_use, mount, yield_kwh)
    capacity_out = {
        "mwp_range": format_mwp_range(cap.get("mwp_lo"), cap.get("mwp_hi")),
        "mwh_range": format_mwh_range(cap.get("mwh_lo"), cap.get("mwh_hi")),
        "mw_per_ha": cap.get("mw_per_ha"),
    }

    # ── Yield (four configs — YieldIQ engine) ─────────────────────────────
    yield_configs: dict = {}
    try:
        results, raddatabase = run_all_configs(
            req.lat, req.lon,
            gcr_1p=req.gcr_1p,
            gcr_2p=req.gcr_2p,
            soiling_loss=2.0,
            other_loss=6.0,
        )
        yield_configs = {
            "raddatabase": raddatabase,
            "configs": {
                name: {
                    "specific_yield_kwh_kwp": res.get("specific_yield"),
                    "pr_pct": res.get("pr"),
                    "gcr": res.get("gcr"),
                    "total_loss_pct": res.get("total_loss"),
                }
                for name, res in results.items()
            },
        }
    except Exception as e:
        errors.append(f"Yield comparison failed: {e}")

    # ── Layout + BOM (LayoutIQ engine) ────────────────────────────────────
    layout_out = None
    bom_out = None
    if req.run_layout and req.boundary and len(req.boundary) >= 3:
        layout = run_layout(
            req.boundary,
            module_h=req.module_h,
            module_w=req.module_w,
            n_portrait=req.n_portrait,
            pitch=req.pitch_m,
            setback=req.setback_m,
            azimuth=180.0,
            mounting_type=mounting_type,
        )
        if layout:
            layout_out = {
                "total_modules": layout["total_modules"],
                "total_rows": layout["total_rows"],
                "area_ha": layout["area_ha"],
                "dc_kwp": round(layout["total_modules"] * req.module_wp / 1000, 1),
            }
            bom_out = compute_bom(
                layout, req.module_wp, req.n_portrait,
                modules_per_string=28,
                strings_per_inv=4,
                inv_ac_kw=100.0,
            )
        else:
            errors.append("Layout failed — boundary too small after setback or pitch too large")

    # ── PVMath score (simplified gate scoring) ────────────────────────────
    scores = {
        "solar": _tier_score(solar_label),
        "terrain": _tier_score(slope_label),
        "flood": _tier_score(flood["risk"]),
        "land": 80 if req.land_use == "Standard" else 72,
        "regulatory": 75,
    }
    pvmath_score = calculate_pvmath_score(scores)
    verdict = get_verdict_from_score(pvmath_score)

    return GateResponse(
        success=len(errors) == 0 or solar.get("success", False),
        project_name=req.project_name,
        coordinates={"lat": req.lat, "lon": req.lon},
        solar={
            "success": solar.get("success", False),
            "annual_ghi": solar.get("annual_ghi"),
            "annual_yield": solar.get("annual_yield"),
            "optimal_tilt": solar.get("optimal_tilt"),
            "rating": solar_label,
            "detail": solar_detail,
        },
        terrain={
            "success": terrain.get("success", False),
            "max_slope_pct": terrain.get("max_slope_pct"),
            "mean_slope_pct": terrain.get("mean_slope_pct"),
            "center_elev_m": terrain.get("center_elev"),
            "sample_points": terrain.get("sample_points"),
            "boundary_sampled": terrain.get("boundary_sampled"),
            "terrain_source": terrain.get("terrain_source"),
            "terrain_source_used": terrain.get("terrain_source_used"),
            "rating": slope_label,
            "detail": slope_detail,
        },
        flood=flood,
        regulatory=regulatory,
        capacity=capacity_out,
        yield_configs=yield_configs,
        layout=layout_out,
        bom=bom_out,
        pvmath_score=pvmath_score,
        verdict=verdict,
        verdict_detail=(
            f"Gate screening for {req.land_use} · {mount}. "
            f"Terrain {'boundary' if polygons else 'pin'} sample. Screening-grade only."
        ),
        errors=errors,
    )
