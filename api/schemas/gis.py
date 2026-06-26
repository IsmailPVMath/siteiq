"""Schemas for SiteIQ intelligent GIS analysis."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from api.schemas.gate import BoundaryPoint


class WorkflowGisAnalysisRequest(BaseModel):
    boundary: Optional[List[BoundaryPoint]] = None
    boundaries: Optional[List[List[BoundaryPoint]]] = None
    restriction_polygons_geojson: Optional[Dict[str, Any]] = None
    setbacks_m: Optional[Dict[str, float]] = None
    constraint_layers: Optional[Dict[str, Any]] = None
    include_grid: bool = True


class ConstraintSummaryItem(BaseModel):
    category: str
    label: str
    feature_count: int
    setback_m: float
    excluded_ha: float
    style: Dict[str, str] = Field(default_factory=dict)


class WorkflowGisAnalysisResponse(BaseModel):
    success: bool
    error: Optional[str] = None
    coordinates: Optional[Dict[str, float]] = None
    site_area_ha: float = 0.0
    buildable_area_ha: float = 0.0
    buildable_pct: float = 0.0
    site_boundary_geojson: Optional[Dict[str, Any]] = None
    buildable_area_geojson: Optional[Dict[str, Any]] = None
    excluded_area_geojson: Optional[Dict[str, Any]] = None
    constraint_layers: Dict[str, Any] = Field(default_factory=dict)
    layer_styles: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    constraint_summary: List[ConstraintSummaryItem] = Field(default_factory=list)
    feature_counts: Dict[str, int] = Field(default_factory=dict)
    setbacks_m: Dict[str, float] = Field(default_factory=dict)
    grid: Optional[Dict[str, Any]] = None
    sources: List[str] = Field(default_factory=list)
    disclaimer: str = ""
    note: str = ""
