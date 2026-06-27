"""
PVMath Site Screening Library — persistent SiteIQ results + PVMath Score.

Scores and weights align with SiteIQ suitability breakdown (siteiq.py).
Database: Supabase table `site_screening_library` + RPC `get_screening_benchmark_stats`.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import requests as _req

from pvmath_auth import _db_hdr, _sb_url

_log = logging.getLogger("pvmath.screening_library")

# Deterministic PVMath Score weights (must sum to 1.0)
_PVMATH_WEIGHTS = {
    "solar": 0.35,
    "terrain": 0.25,
    "flood": 0.15,
    "land": 0.15,
    "regulatory": 0.10,
}

BENCHMARK_MIN_GLOBAL = 50
BENCHMARK_MIN_COUNTRY = 20


def calculate_pvmath_score(scores: dict) -> int:
    """Weighted PVMath Score from category scores (0–100 each)."""
    raw = (
        float(scores.get("solar", 0)) * _PVMATH_WEIGHTS["solar"]
        + float(scores.get("terrain", 0)) * _PVMATH_WEIGHTS["terrain"]
        + float(scores.get("flood", 0)) * _PVMATH_WEIGHTS["flood"]
        + float(scores.get("land", 0)) * _PVMATH_WEIGHTS["land"]
        + float(scores.get("regulatory", 0)) * _PVMATH_WEIGHTS["regulatory"]
    )
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


def _slope_confidence_label(terrain: dict) -> str:
    if (terrain.get("terrainiq_confirmed") or terrain.get("topoiq_confirmed")):
        return "High — TerrainIQ GLO-30 grid confirmed"
    if terrain.get("boundary_sampled"):
        return "Low — sparse OpenTopoData boundary sample"
    if terrain.get("success"):
        return "Medium — pin-radius elevation sample"
    return "Unknown — terrain data unavailable"


def _flood_label_clean(flood_risk: str) -> str:
    for prefix in ("🟢 ", "🟡 ", "🟠 ", "🔴 ", "⚠️ "):
        flood_risk = (flood_risk or "").replace(prefix, "")
    return flood_risk.strip() or "Unknown"


def _extract_region(location_label: str, project_country: str) -> Optional[str]:
    """Best-effort region/state from reverse-geocode label."""
    if not location_label:
        return None
    parts = [p.strip() for p in location_label.split(",") if p.strip()]
    if len(parts) >= 2:
        # e.g. "Tehuacana, Texas, United States" -> Texas
        candidate = parts[-2] if "united states" in parts[-1].lower() else parts[1]
        if candidate.lower() != (project_country or "").lower():
            return candidate
    return None


def build_screening_record(
    *,
    user_id: str,
    project_name: str,
    lat: float,
    lon: float,
    area_ha: float,
    land_use: str,
    mount_type: str,
    solar: dict,
    terrain: dict,
    cap: dict,
    flood: dict,
    scores: dict,
    pvmath_score: int,
    verdict_label: str,
    module_confidence: str,
    country: str,
    project_country: str,
    location_label: str = "",
    eeg_status: str = "",
    coord_note: str = "",
    project_row_id=None,
    used_topo_cache: bool = False,
) -> dict:
    """Build a row dict for site_screening_library."""
    report_id = str(uuid.uuid4())
    ghi = solar.get("annual_ghi") if solar.get("success") else None
    poa = solar.get("annual_poa") or ghi  # POA when available; else in-plane proxy
    spec_y = solar.get("annual_yield") if solar.get("success") else None

    max_slope = terrain.get("max_slope_pct") if terrain.get("success") else None
    mean_slope = terrain.get("mean_slope_pct") if (terrain.get("terrainiq_confirmed") or terrain.get("topoiq_confirmed")) else None

    data_sources = (
        "PVGIS JRC; OpenTopoData EU-DEM/SRTM"
        + ("; TerrainIQ Copernicus GLO-30" if (terrain.get("terrainiq_confirmed") or terrain.get("topoiq_confirmed")) else "")
        + "; OpenStreetMap/Nominatim"
    )

    raw_inputs = {
        "project_row_id": project_row_id,
        "coord_note": coord_note,
        "used_topo_cache": used_topo_cache,
        "land_use": land_use,
        "mount_type": mount_type,
        "project_country_input": project_country,
    }
    raw_outputs = {
        "scores": scores,
        "pvmath_score": pvmath_score,
        "verdict_label": verdict_label,
        "eeg_status": eeg_status,
        "flood_reason": flood.get("reason"),
        "terrain": {
            k: terrain.get(k)
            for k in (
                "terrainiq_confirmed", "boundary_sampled", "sample_points",
                "grid_m", "center_elev",
            )
        },
        "solar_radiation_db": solar.get("radiation_db"),
    }

    return {
        "user_id": user_id,
        "project_name": (project_name or "").strip() or None,
        "country": (project_country or country or "").strip() or None,
        "region_state": _extract_region(location_label, project_country),
        "latitude": lat,
        "longitude": lon,
        "site_area_ha": area_ha,
        "land_use_type": land_use,
        "mounting_system": mount_type,
        "ghi_kwh_m2_yr": ghi,
        "poa_kwh_m2_yr": poa,
        "specific_yield_kwh_kwp_yr": spec_y,
        "estimated_capacity_min_mwp": cap.get("mwp_lo"),
        "estimated_capacity_max_mwp": cap.get("mwp_hi"),
        "estimated_output_min_mwh_yr": cap.get("mwh_lo"),
        "estimated_output_max_mwh_yr": cap.get("mwh_hi"),
        "max_slope_percent": max_slope,
        "mean_slope_percent": mean_slope,
        "slope_confidence": _slope_confidence_label(terrain),
        "flood_risk_label": _flood_label_clean(flood.get("risk", "")),
        "flood_confidence": flood.get("confidence"),
        "solar_resource_score": scores.get("solar"),
        "terrain_score": scores.get("terrain"),
        "flood_risk_score": scores.get("flood"),
        "land_use_score": scores.get("land"),
        "grid_regulatory_score": scores.get("regulatory"),
        "pvmath_score": pvmath_score,
        "verdict_label": verdict_label,
        "module_confidence": module_confidence,
        "data_sources_used": data_sources,
        "report_id": report_id,
        "report_pdf_url": None,
        "raw_inputs_json": raw_inputs,
        "raw_outputs_json": raw_outputs,
    }


def save_site_screening_result(record: dict) -> Optional[str]:
    """
    Insert one screening row. Returns report_id on success, None on failure.
    Never raises — logs errors for ops visibility.
    """
    if not record.get("user_id"):
        _log.warning("save_site_screening_result: missing user_id — skipped")
        return None
    try:
        r = _req.post(
            f"{_sb_url()}/rest/v1/site_screening_library",
            json=record,
            headers={**_db_hdr(), "Prefer": "return=representation"},
            timeout=15,
        )
        if r.status_code in (200, 201):
            rows = r.json()
            if rows and isinstance(rows, list):
                rid = rows[0].get("report_id") or record.get("report_id")
                _log.info(
                    "Saved site screening library row report_id=%s user=%s score=%s",
                    rid, record.get("user_id"), record.get("pvmath_score"),
                )
                return str(rid) if rid else None
        _log.warning(
            "save_site_screening_result failed: HTTP %s %s",
            r.status_code, r.text[:300],
        )
    except Exception as exc:
        _log.warning("save_site_screening_result exception: %s", exc)
    return None


def get_user_screening_history(user_id: str, limit: int = 50) -> list:
    """Recent screenings for the signed-in user (newest first)."""
    if not user_id:
        return []
    try:
        r = _req.get(
            f"{_sb_url()}/rest/v1/site_screening_library",
            params={
                "user_id": f"eq.{user_id}",
                "select": (
                    "id,report_id,project_name,created_at,country,pvmath_score,"
                    "verdict_label,site_area_ha,latitude,longitude"
                ),
                "order": "created_at.desc",
                "limit": str(limit),
            },
            headers=_db_hdr(),
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, list) else []
    except Exception as exc:
        _log.warning("get_user_screening_history exception: %s", exc)
    return []


def get_global_benchmark_summary(
    pvmath_score: int,
    country: str = "",
) -> dict:
    """
    Anonymized benchmark stats via Supabase RPC (no other users' data exposed).
    Returns benchmark_ready=False until >= 50 global records exist.
    """
    base = {
        "benchmark_ready": False,
        "global_count": 0,
        "global_percentile": None,
        "global_average": None,
        "top_quartile_threshold": None,
        "country_count": 0,
        "country_percentile": None,
        "status_message": (
            "Benchmarking requires more PVMath screening history. "
            "Current score is based on deterministic engineering rules."
        ),
    }
    try:
        r = _req.post(
            f"{_sb_url()}/rest/v1/rpc/get_screening_benchmark_stats",
            json={
                "p_pvmath_score": int(pvmath_score),
                "p_country": (country or "").strip() or None,
            },
            headers=_db_hdr(),
            timeout=15,
        )
        if r.status_code != 200:
            _log.warning("benchmark RPC failed: HTTP %s", r.status_code)
            return base
        data = r.json()
        if not isinstance(data, dict):
            return base
        base.update(data)
        if base.get("benchmark_ready"):
            parts = []
            if base.get("global_percentile") is not None:
                parts.append(
                    f"Global percentile: {base['global_percentile']:.0f} "
                    f"(n={base.get('global_count', 0)} anonymized screenings)"
                )
            if base.get("global_average") is not None:
                parts.append(f"Platform average PVMath Score: {base['global_average']}")
            if base.get("top_quartile_threshold") is not None:
                parts.append(
                    f"Top-quartile threshold: {base['top_quartile_threshold']}/100"
                )
            if base.get("country_percentile") is not None:
                parts.append(
                    f"{country} percentile: {base['country_percentile']:.0f} "
                    f"(n={base.get('country_count', 0)})"
                )
            base["status_message"] = " · ".join(parts) if parts else base["status_message"]
        return base
    except Exception as exc:
        _log.warning("get_global_benchmark_summary exception: %s", exc)
        return base


def format_pvmath_score_pdf_block(
    pvmath_score: int,
    verdict_label: str,
    benchmark: dict,
) -> list[str]:
    """Plain-text lines for PDF PVMath Score section."""
    lines = [
        f"PVMath Score: {pvmath_score}/100",
        f"Verdict: {verdict_label}",
        "Score basis: Deterministic engineering screening model",
        f"Benchmark status: {benchmark.get('status_message', '')}",
    ]
    return lines
