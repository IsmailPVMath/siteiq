"""Run LayoutIQ electrical screening from layout detail geometry."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from layoutiq.electrical import compute_electrical
from pvmath_workflow.project_report import _merged_layout_for_drawing


def build_layout_electrical(
    detail: Dict[str, Any],
    *,
    module_name: str,
    inverter_name: str,
    system_voltage_v: int = 1500,
    dc_ac_ratio: float = 1.20,
    strings_per_combiner: int = 12,
    lat: Optional[float] = None,
    pitch_m: Optional[float] = None,
    mount_type: str = "",
    tmy_t2m: Optional[List[float]] = None,
    module_override: Optional[Dict[str, Any]] = None,
    inverter_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    layout = _merged_layout_for_drawing(detail)
    if not layout:
        raise ValueError("Layout geometry missing for electrical calculation")
    ref_lat = lat if lat is not None else detail.get("ref_lat")
    pitch = pitch_m if pitch_m is not None else float(detail.get("pitch_m") or 6.0)
    mount = mount_type or str(detail.get("mount_type") or "")
    return compute_electrical(
        layout=layout,
        module_name=module_name,
        inverter_name=inverter_name,
        system_voltage_v=system_voltage_v,
        dc_ac_ratio=dc_ac_ratio,
        strings_per_combiner=strings_per_combiner,
        lat=ref_lat,
        tmy_t2m=tmy_t2m,
        pitch_m=pitch,
        mount_type=mount,
        module_override=module_override,
        inverter_override=inverter_override,
    )
