"""Versioned Project Setup schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from api.schemas.projects import ProjectPayload


class SetupValidationIssue(BaseModel):
    level: Literal["error", "warning"]
    field: Optional[str] = None
    message: str


class WorkflowReadiness(BaseModel):
    has_boundary: bool = False
    can_run_siteiq: bool = False
    can_run_terrainiq: bool = False
    can_run_layoutiq: bool = False
    can_run_yieldiq: bool = False


class ProjectSetupValidateResponse(BaseModel):
    valid: bool
    issues: List[SetupValidationIssue]
    readiness: WorkflowReadiness
    modules_to_run: List[str] = Field(default_factory=list)


class ProjectSetupValidateRequest(BaseModel):
    project_data: Dict[str, Any] = Field(default_factory=dict)


class ProjectPartialUpdateRequest(BaseModel):
    """Partial update — only provided top-level keys are merged."""

    name: Optional[str] = None
    center: Optional[Dict[str, float]] = None
    site_boundary_geojson: Optional[Dict[str, Any]] = None
    restriction_polygons_geojson: Optional[Dict[str, Any]] = None
    buildable_area_geojson: Optional[Dict[str, Any]] = None
    land_use: Optional[str] = None
    mount_type: Optional[str] = None
    country: Optional[str] = None
    workflow: Optional[Dict[str, Any]] = None
    project_info: Optional[Dict[str, Any]] = None
    location: Optional[Dict[str, Any]] = None
    geometry: Optional[Dict[str, Any]] = None
    design_basis: Optional[Dict[str, Any]] = None
    assumptions: Optional[Dict[str, Any]] = None
    schema_version: Optional[int] = None


class VersionedProjectPayload(ProjectPayload):
    schema_version: int = Field(default=1)
    project_info: Dict[str, Any] = Field(default_factory=dict)
    location: Dict[str, Any] = Field(default_factory=dict)
    geometry: Dict[str, Any] = Field(default_factory=dict)
    design_basis: Dict[str, Any] = Field(default_factory=dict)
    assumptions: Dict[str, Any] = Field(default_factory=dict)
