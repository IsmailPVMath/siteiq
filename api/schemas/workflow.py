"""Pydantic schemas for unified React workflow API."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from api.schemas.gate import BoundaryPoint


class WorkflowScreenRequest(BaseModel):
    project_name: str = Field(default="Site screening", max_length=200)
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    area_ha: float = Field(..., gt=0, le=100_000)
    land_use: Literal["Standard", "Agri-PV"] = "Standard"
    mount_type: str = Field(default="Fixed Tilt")
    country: str = Field(default="", max_length=120)


class WorkflowScreenResponse(BaseModel):
    success: bool
    project_name: str
    coordinates: Dict[str, float]
    solar: Dict[str, Any]
    flood: Dict[str, Any]
    regulatory: Dict[str, Any]
    capacity: Dict[str, Any]
    score_components: Dict[str, int]
    terrain_note: str
    errors: List[str]


class WorkflowScoreRequest(BaseModel):
    score_components: Dict[str, int] = Field(
        ...,
        description="Partial scores from workflow/screen (solar, flood, land, regulatory).",
    )
    terrain_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="TopoIQ terrain_score from terrain_drivers — authoritative terrain input.",
    )


class WorkflowScoreResponse(BaseModel):
    pvmath_score: int
    verdict: str
    components: Dict[str, int]
    verdict_detail: str


class WorkflowLayoutMatrixRequest(BaseModel):
    boundary: List[BoundaryPoint] = Field(..., min_length=3)
    module_h: float = Field(default=2.094, gt=0)
    module_w: float = Field(default=1.038, gt=0)
    module_wp: int = Field(default=550, ge=200, le=1000)
    pitch_m: Optional[float] = Field(default=None, gt=0)
    setback_m: float = Field(default=5.0, ge=0)
    azimuth: float = Field(default=180.0, ge=90, le=270)
    modules_per_string: int = Field(default=28, ge=8, le=50)
    strings_per_inv: int = Field(default=4, ge=1, le=50)
    inv_ac_kw: float = Field(default=100.0, gt=0)


class WorkflowLayoutMatrixResponse(BaseModel):
    configs: List[Dict[str, Any]]
