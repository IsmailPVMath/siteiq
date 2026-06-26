"""Pydantic schemas for TopoIQ API."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class TopoIQAnalyzeRequest(BaseModel):
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


class TopoIQVerdict(BaseModel):
    label: str
    detail: str


class TopoIQAnalyzeResponse(BaseModel):
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
    verdict_fixed: TopoIQVerdict
    verdict_tracker: TopoIQVerdict
    terrain_drivers: Dict[str, Any]
    contour_minor: float
    contour_major: float
    disclaimer: str
    bbox: Dict[str, float]
    route_note: Optional[str] = None
