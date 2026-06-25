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
    grid: Dict[str, Any]
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


class WorkflowLayoutSweepRequest(BaseModel):
    boundary: Optional[List[BoundaryPoint]] = None
    boundaries: Optional[List[List[BoundaryPoint]]] = Field(
        default=None,
        description="Multiple enabled parcels; analysed in one shared metric frame.",
    )
    module_h: float = Field(default=2.094, gt=0)
    module_w: float = Field(default=1.038, gt=0)
    module_wp: int = Field(default=550, ge=200, le=1000)
    setback_m: float = Field(default=5.0, ge=0)
    azimuth: float = Field(default=180.0, ge=90, le=270)
    pitch_steps_m: Optional[List[float]] = Field(
        default=None,
        description="Optional pitch list (m). Defaults to standard sweep from min pitch upward.",
    )
    include_bom: bool = False


class WorkflowLayoutSweepResponse(BaseModel):
    rows: List[Dict[str, Any]]
    best_by_config: Dict[str, Any]
    config_count: int
    row_count: int


class WorkflowLayoutDetailRequest(BaseModel):
    project_name: str = Field(default="LayoutIQ", max_length=200)
    boundary: Optional[List[BoundaryPoint]] = None
    boundaries: Optional[List[List[BoundaryPoint]]] = None
    config_key: str = Field(..., max_length=16)
    pitch_m: float = Field(..., gt=0)
    module_h: float = Field(default=2.094, gt=0)
    module_w: float = Field(default=1.038, gt=0)
    module_wp: int = Field(default=550, ge=200, le=1000)
    setback_m: float = Field(default=5.0, ge=0)
    azimuth: float = Field(default=180.0, ge=90, le=270)


class WorkflowLayoutDetailResponse(BaseModel):
    config_key: str
    label: str
    mount_type: str
    n_portrait: int
    pitch_m: float
    gcr: float
    total_modules: int
    total_rows: int
    area_ha: float
    dc_kwp: float
    ref_lat: float
    ref_lon: float
    geojson: Dict[str, Any]


class WorkflowTerrainMeshRequest(BaseModel):
    boundary: Optional[List[BoundaryPoint]] = None
    boundaries: Optional[List[List[BoundaryPoint]]] = None
    grid_m: float = Field(default=20.0, ge=5.0, le=100.0)
    max_vertices: int = Field(default=12_000, ge=1_000, le=40_000)


class WorkflowTerrainMeshResponse(BaseModel):
    vertices: List[List[float]]
    faces: List[List[int]]
    elevations: List[float]
    slopes: List[float]
    origin: Dict[str, float]
    bbox: Dict[str, float]
    grid_m_used: float
    terrain_source_used: str
    z_min: float
    z_max: float
    slope_mean: float
