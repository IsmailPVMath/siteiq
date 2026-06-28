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
        description="TerrainIQ terrain_score from terrain_drivers — authoritative terrain input.",
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
    restriction_polygons: Optional[List[List[BoundaryPoint]]] = Field(
        default=None,
        description="Manual no-build polygons subtracted from buildable area.",
    )
    module_h: float = Field(default=2.094, gt=0)
    module_w: float = Field(default=1.038, gt=0)
    module_wp: int = Field(default=550, ge=200, le=1000)
    setback_m: float = Field(default=5.0, ge=0)
    azimuth: float = Field(default=180.0, ge=90, le=270)
    pitch_steps_m: Optional[List[float]] = Field(
        default=None,
        description="Optional extra pitch values (m) added to the mode-specific sweep.",
    )
    optimization_mode: Literal["high_energy", "balanced", "land_optimized", "custom"] = Field(
        default="balanced",
        description="GCR strategy: high energy (wider), balanced defaults, land optimized (tighter), or custom.",
    )
    land_cost: Literal["auto", "cheap", "balanced", "expensive"] = Field(
        default="auto",
        description="Land-cost class; auto infers from country / latitude.",
    )
    country: str = Field(default="", max_length=120)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    bifacial: bool = False
    custom_gcr: Optional[float] = Field(default=None, gt=0, le=0.85)
    custom_pitch_m: Optional[float] = Field(default=None, gt=0, le=30)
    include_bom: bool = False
    modules_per_string: int = Field(default=28, ge=8, le=50)
    inter_string_gap_m: float = Field(default=0.5, ge=0, le=2.0)
    tracker_string_options: List[int] = Field(default_factory=lambda: [8, 7, 6, 5])
    max_tracker_length_m: float = Field(default=260.0, gt=0, le=500.0)
    rows_per_block: int = Field(default=0, ge=0, le=10)
    block_gap_m: float = Field(default=0.0, ge=0, le=20.0)
    cols_per_block: int = Field(default=0, ge=0, le=200)
    ew_gap_m: float = Field(default=0.0, ge=0, le=30.0)
    road_mode: Literal["auto", "manual", "off"] = Field(default="off")
    road_preset: str = Field(default="no_roads", max_length=32)
    exclude_tracker_slope: bool = Field(default=False)
    tracker_slope_limit_pct: float = Field(default=6.0, ge=0.5, le=30.0)
    slope_restriction_grid_m: float = Field(default=20.0, ge=5.0, le=100.0)
    mount_filter: Literal["all", "fixed", "sat"] = Field(
        default="all",
        description="Limit sweep to the mount type chosen in project setup.",
    )
    portrait_filter: Optional[List[int]] = Field(
        default=None,
        description="Limit sweep to specific module-portrait counts (e.g. [1] or [2]). None sweeps all portraits for the mount.",
    )
    row_alignment: Literal["horizontal", "boundary"] = Field(
        default="horizontal",
        description="horizontal = uniform rows from south/west fence; boundary = pack along parcel edge pockets.",
    )
    allow_partial_strings: bool = Field(
        default=False,
        description="Place half-strings (≥50% modules) at row ends when space remains; otherwise stop at last complete string.",
    )


class WorkflowLayoutSweepResponse(BaseModel):
    rows: List[Dict[str, Any]]
    best_by_config: Dict[str, Any]
    recommended_by_config: Dict[str, Any] = Field(default_factory=dict)
    gcr_guidance: Dict[str, Any] = Field(default_factory=dict)
    strategy: Dict[str, Any] = Field(default_factory=dict)
    layout_params: Dict[str, Any] = Field(default_factory=dict)
    config_count: int
    row_count: int


class WorkflowLayoutDetailRequest(BaseModel):
    project_name: str = Field(default="LayoutIQ", max_length=200)
    boundary: Optional[List[BoundaryPoint]] = None
    boundaries: Optional[List[List[BoundaryPoint]]] = None
    restriction_polygons: Optional[List[List[BoundaryPoint]]] = None
    config_key: str = Field(..., max_length=16)
    pitch_m: float = Field(..., gt=0)
    module_h: float = Field(default=2.094, gt=0)
    module_w: float = Field(default=1.038, gt=0)
    module_wp: int = Field(default=550, ge=200, le=1000)
    setback_m: float = Field(default=5.0, ge=0)
    azimuth: float = Field(default=180.0, ge=90, le=270)
    modules_per_string: int = Field(default=28, ge=8, le=50)
    inter_string_gap_m: float = Field(default=0.5, ge=0, le=2.0)
    tracker_string_options: List[int] = Field(default_factory=lambda: [8, 7, 6, 5])
    max_tracker_length_m: float = Field(default=260.0, gt=0, le=500.0)
    rows_per_block: int = Field(default=0, ge=0, le=10)
    block_gap_m: float = Field(default=0.0, ge=0, le=20.0)
    cols_per_block: int = Field(default=0, ge=0, le=200)
    ew_gap_m: float = Field(default=0.0, ge=0, le=30.0)
    road_mode: Literal["auto", "manual", "off"] = Field(default="off")
    road_preset: str = Field(default="no_roads", max_length=32)
    exclude_tracker_slope: bool = Field(default=False)
    tracker_slope_limit_pct: float = Field(default=6.0, ge=0.5, le=30.0)
    slope_restriction_grid_m: float = Field(default=20.0, ge=5.0, le=100.0)
    allow_partial_strings: bool = Field(default=False)
    row_alignment: Literal["horizontal", "boundary"] = Field(
        default="horizontal",
        description="horizontal = uniform rows from south/west fence; boundary = pack along parcel edge pockets.",
    )


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
    dc_mwp: Optional[float] = None
    mw_per_ha: Optional[float] = None
    ref_lat: float
    ref_lon: float
    geojson: Dict[str, Any]


class WorkflowTerrainMeshRequest(BaseModel):
    boundary: Optional[List[BoundaryPoint]] = None
    boundaries: Optional[List[List[BoundaryPoint]]] = None
    grid_m: float = Field(default=20.0, ge=5.0, le=100.0)
    max_vertices: int = Field(default=12_000, ge=1_000, le=40_000)
    mask_geojson: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional SiteIQ buildable-area GeoJSON to clip terrain to buildable land.",
    )


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


class WorkflowPvmathReportRequest(BaseModel):
    project_name: str = Field(default="Project", max_length=200)
    country: str = Field(default="", max_length=120)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)
    land_use: str = Field(default="Standard", max_length=40)
    screening: Optional[Dict[str, Any]] = None
    topo: Optional[Dict[str, Any]] = None
    score: Optional[Dict[str, Any]] = None
    layout_row: Optional[Dict[str, Any]] = None
    yield_result: Optional[Dict[str, Any]] = None
    selected_yield_mwh: Optional[float] = None


class WorkflowProjectPackageRequest(WorkflowPvmathReportRequest):
    boundary: Optional[List[BoundaryPoint]] = None
    boundaries: Optional[List[List[BoundaryPoint]]] = None
    restriction_polygons: Optional[List[List[BoundaryPoint]]] = None
    config_key: str = Field(..., max_length=16)
    pitch_m: float = Field(..., gt=0)
    module_h: float = Field(default=2.094, gt=0)
    module_w: float = Field(default=1.038, gt=0)
    module_wp: int = Field(default=550, ge=200, le=1000)
    setback_m: float = Field(default=5.0, ge=0)
    azimuth: float = Field(default=180.0, ge=90, le=270)
    modules_per_string: int = Field(default=28, ge=8, le=50)
    inter_string_gap_m: float = Field(default=0.5, ge=0, le=2.0)
    tracker_string_options: List[int] = Field(default_factory=lambda: [8, 7, 6, 5])
    max_tracker_length_m: float = Field(default=260.0, gt=0, le=500.0)
    rows_per_block: int = Field(default=0, ge=0, le=10)
    block_gap_m: float = Field(default=0.0, ge=0, le=20.0)
    cols_per_block: int = Field(default=0, ge=0, le=200)
    ew_gap_m: float = Field(default=0.0, ge=0, le=30.0)
    road_mode: Literal["auto", "manual", "off"] = Field(default="off")
    road_preset: str = Field(default="no_roads", max_length=32)
    exclude_tracker_slope: bool = Field(default=False)
    tracker_slope_limit_pct: float = Field(default=6.0, ge=0.5, le=30.0)
    slope_restriction_grid_m: float = Field(default=20.0, ge=5.0, le=100.0)
