"""Pydantic schemas for TerrainIQ API."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class TerrainIQAnalyzeRequest(BaseModel):
    project_name: str = Field(default="Terrain analysis", max_length=200)
    country: str = Field(default="", max_length=120)
    land_use: Literal["Standard", "Agri-PV"] = "Standard"
    polygons: List[List[Any]] = Field(
        ...,
        description="List of polygon rings. Points can be {lat, lon} or [lon, lat].",
    )
    grid_m: float = Field(default=5.0, gt=0)
    allow_coarsen: bool = False
    contour_minor: float = Field(default=0.5, gt=0)
    contour_major: float = Field(default=1.0, gt=0)
    mask_geojson: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional SiteIQ buildable-area GeoJSON to clip terrain to buildable land.",
    )


class TerrainIQVerdict(BaseModel):
    label: str
    detail: str


class TerrainCoverageGap(BaseModel):
    polygon_indices: List[int] = Field(
        default_factory=list,
        description="0-based indices into the submitted boundary polygon list.",
    )
    area_ha: float = 0.0
    reason_code: str = "UNKNOWN"
    message: str = ""


class TerrainIQAnalyzeResponse(BaseModel):
    project_name: str
    country: str
    land_use: str
    area_ha: float
    grid_m_requested: float
    grid_m_used: float
    grid_points: int
    dem_zoom: int
    tile_count: int
    terrain_source_used: str
    terrain_source: Dict[str, Any]
    elevation: Dict[str, float]
    slope: Dict[str, Any]
    extras: Dict[str, Any]
    verdict_fixed: TerrainIQVerdict
    verdict_tracker: TerrainIQVerdict
    terrain_drivers: Dict[str, Any]
    contour_minor: float
    contour_major: float
    disclaimer: str
    bbox: Dict[str, float]
    route_note: Optional[str] = None
    coverage_gaps: List[TerrainCoverageGap] = Field(default_factory=list)
    polygons_analyzed: List[int] = Field(default_factory=list)
    multi_cluster: bool = False
    cluster_count: int = 1
