"""Gate analysis request/response models (plain dataclasses + API schemas)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GateRequest:
    project_name: str = "Gate analysis"
    lat: float = 0.0
    lon: float = 0.0
    area_ha: float = 0.0
    land_use: str = "Standard"
    mount_type: str = "Fixed Tilt"
    country: str = ""
    boundary: list[list[float]] | None = None  # [[lat, lon], ...]
    run_layout: bool = True
    module_h: float = 2.094
    module_w: float = 1.038
    module_wp: int = 550
    n_portrait: int = 2
    pitch_m: float = 5.0
    setback_m: float = 5.0
    gcr_1p: float = 0.35
    gcr_2p: float = 0.42


@dataclass
class GateResponse:
    success: bool
    project_name: str
    coordinates: dict[str, float]
    solar: dict[str, Any] = field(default_factory=dict)
    terrain: dict[str, Any] = field(default_factory=dict)
    flood: dict[str, Any] = field(default_factory=dict)
    regulatory: dict[str, Any] = field(default_factory=dict)
    capacity: dict[str, Any] = field(default_factory=dict)
    yield_configs: dict[str, Any] = field(default_factory=dict)
    layout: dict[str, Any] | None = None
    bom: dict[str, str] | None = None
    pvmath_score: int | None = None
    verdict: str = ""
    verdict_detail: str = ""
    errors: list[str] = field(default_factory=list)
    api_version: str = "v1"
