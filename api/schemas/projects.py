"""Schemas for project CRUD and buildable-area computation."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ProjectPayload(BaseModel):
    name: str = Field(default="New project", max_length=200)
    center: Dict[str, float] = Field(default_factory=dict)
    site_boundary_geojson: Optional[Dict[str, Any]] = None
    restriction_polygons_geojson: Optional[Dict[str, Any]] = None
    buildable_area_geojson: Optional[Dict[str, Any]] = None
    land_use: str = Field(default="Standard")
    mount_type: str = Field(default="Fixed Tilt")
    country: str = Field(default="")
    workflow: Dict[str, Any] = Field(default_factory=dict)


class ProjectRecord(BaseModel):
    id: str
    user_id: str
    project_data: Dict[str, Any]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProjectUpsertRequest(ProjectPayload):
    pass


class BuildableAreaRequest(BaseModel):
    site_boundary_geojson: Dict[str, Any]
    restriction_polygons_geojson: Optional[Dict[str, Any]] = None


class BuildableAreaResponse(BaseModel):
    buildable_area_geojson: Optional[Dict[str, Any]] = None
    buildable_area_ha: float
