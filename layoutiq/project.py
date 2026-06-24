"""Load boundary + defaults from Streamlit project session state."""

from __future__ import annotations

from typing import Any


def _poly_area_ha(coords: list) -> float:
    if len(coords) < 3:
        return 0.0
    # Shoelace in degree space — rough sort for picking largest parcel only.
    area = 0.0
    n = len(coords)
    for i in range(n):
        lat1, lon1 = coords[i]
        lat2, lon2 = coords[(i + 1) % n]
        area += lon1 * lat2 - lon2 * lat1
    return abs(area) / 2.0


def load_project_context(session_state: dict[str, Any]) -> dict[str, Any]:
    """
    Read saved Project Setup boundary for layout handoff.

    Returns dict with keys:
      latlons, source, project_name, area_ha, suggested_pitch, suggested_mount
    """
    proj = session_state.get("pvm_project") or {}
    latlons = None
    source = ""

    if proj.get("polygon_coords") and len(proj["polygon_coords"]) >= 3:
        latlons = list(proj["polygon_coords"])
        source = "saved project boundary"
    else:
        bounds = proj.get("polygon_boundaries") or session_state.get("proj_boundaries") or []
        enabled = [b for b in bounds if b.get("enabled") and b.get("coords")]
        if enabled:
            primary = max(enabled, key=lambda b: _poly_area_ha(b["coords"]))
            latlons = list(primary["coords"])
            source = primary.get("name") or "project boundary"

    topoiq = proj.get("topoiq_cache") or {}
    mount_hint = "sat" if "tracker" in str(topoiq.get("mount_type", "")).lower() else "fixed_tilt"

    return {
        "latlons": latlons,
        "source": source,
        "project_name": (proj.get("name") or "").strip(),
        "area_ha": proj.get("area_ha"),
        "suggested_mount": mount_hint,
        "suggested_pitch": 5.5 if mount_hint == "sat" else 5.0,
        "has_topoiq": bool(topoiq.get("verdict") or topoiq.get("slope_stats")),
    }
