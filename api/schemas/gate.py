"""Pydantic schemas for gate analysis API."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class BoundaryPoint(BaseModel):
    lat: float
    lon: float


class GateAnalyzeRequest(BaseModel):
    project_name: str = Field(default="Gate analysis", max_length=200)
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    area_ha: float = Field(..., gt=0, le=100_000)
    land_use: Literal["Standard", "Agri-PV"] = "Standard"
    mount_type: str = Field(default="Fixed Tilt")
    country: str = Field(default="", max_length=120)
    boundary: Optional[List[BoundaryPoint]] = Field(
        default=None,
        description="Site polygon (≥3 points). Enables boundary terrain + layout.",
    )
    run_layout: bool = True
    module_h: float = Field(default=2.094, gt=0)
    module_w: float = Field(default=1.038, gt=0)
    module_wp: int = Field(default=550, ge=200, le=1000)
    n_portrait: int = Field(default=2, ge=1, le=2)
    pitch_m: float = Field(default=5.0, gt=0)
    setback_m: float = Field(default=5.0, ge=0)
    gcr_1p: float = Field(default=0.35, gt=0, le=1)
    gcr_2p: float = Field(default=0.42, gt=0, le=1)


class GateAnalyzeResponse(BaseModel):
    success: bool
    project_name: str
    coordinates: Dict[str, float]
    solar: Dict[str, Any]
    terrain: Dict[str, Any]
    flood: Dict[str, Any]
    regulatory: Dict[str, Any]
    capacity: Dict[str, Any]
    yield_configs: Dict[str, Any]
    layout: Optional[Dict[str, Any]] = None
    bom: Optional[Dict[str, str]] = None
    pvmath_score: Optional[int] = None
    verdict: str
    verdict_detail: str
    errors: List[str]
    api_version: str = "v1"
