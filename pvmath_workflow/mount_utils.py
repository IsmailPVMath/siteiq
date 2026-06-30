"""Resolve mount type and YieldIQ config keys from LayoutIQ selections."""

from __future__ import annotations

from typing import Any, Mapping, Optional


def layout_row_is_tracker(layout_row: Mapping[str, Any] | None) -> bool:
    if not layout_row:
        return False
    mount = str(layout_row.get("mount_type") or "")
    config_key = str(layout_row.get("config_key") or "").upper()
    return "Tracker" in mount or config_key.startswith("SAT")


def resolve_mount_type(
    mount_type: str = "",
    layout_row: Mapping[str, Any] | None = None,
) -> str:
    """Authoritative mount for YieldIQ / PDF — prefer selected LayoutIQ row."""
    if layout_row_is_tracker(layout_row):
        return "Single-Axis Tracker"
    if layout_row:
        mount = str(layout_row.get("mount_type") or "")
        config_key = str(layout_row.get("config_key") or "").upper()
        if "Fixed" in mount or config_key.startswith("FT"):
            return "Fixed Tilt"
    mt = (mount_type or "").strip()
    if "Tracker" in mt:
        return "Single-Axis Tracker"
    if mt in ("Compare FT & SAT", "Compare FT & SAT ", ""):
        return "Fixed Tilt"
    return mt or "Fixed Tilt"


def yield_config_key_from_layout_row(layout_row: Mapping[str, Any] | None) -> Optional[str]:
    if not layout_row:
        return None
    try:
        n_portrait = int(layout_row.get("n_portrait") or 1)
    except (TypeError, ValueError):
        n_portrait = 1
    portrait = "1P" if n_portrait == 1 else "2P"
    kind = "Tracker" if layout_row_is_tracker(layout_row) else "Fixed"
    return f"{portrait} {kind}"


def yield_mount_filter(
    layout_mount_type: str = "",
    layout_row: Mapping[str, Any] | None = None,
) -> str:
    """Return 'sat', 'fixed', or 'all' for YieldIQ display filtering."""
    if layout_row:
        return "sat" if layout_row_is_tracker(layout_row) else "fixed"
    lm = (layout_mount_type or "").strip()
    if lm == "Single-Axis Tracker":
        return "sat"
    if lm == "Fixed Tilt":
        return "fixed"
    return "all"
