"""Schemas for project CRUD and buildable-area computation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProjectPayload(BaseModel):
    name: str = Field(default="New project", max_length=200)
    center: dict[str, float] = Field(default_factory=dict)
    site_boundary_geojson: dict[str, Any] | None = None
    restriction_polygons_geojson: dict[str, Any] | None = None
    buildable_area_geojson: dict[str, Any] | None = None
    land_use: str = Field(default="Standard")
    mount_type: str = Field(default="Fixed Tilt")
    country: str = Field(default="")
    workflow: dict[str, Any] = Field(default_factory=dict)


class ProjectRecord(BaseModel):
    id: str
    user_id: str
    project_data: dict[str, Any]
    created_at: str | None = None
    updated_at: str | None = None


class ProjectUpsertRequest(ProjectPayload):
    pass


class BuildableAreaRequest(BaseModel):
    site_boundary_geojson: dict[str, Any]
    restriction_polygons_geojson: dict[str, Any] | None = None


class BuildableAreaResponse(BaseModel):
    buildable_area_geojson: dict[str, Any] | None
    buildable_area_ha: float
