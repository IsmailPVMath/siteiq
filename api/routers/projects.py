"""Projects CRUD and buildable-area endpoints."""

from __future__ import annotations

import math
from typing import Any

import requests
from fastapi import APIRouter, Depends, HTTPException
from shapely.geometry import GeometryCollection, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from api.deps import get_current_user
from api.schemas.project_setup import (
    ProjectPartialUpdateRequest,
    ProjectSetupValidateRequest,
    ProjectSetupValidateResponse,
)
from api.schemas.projects import (
    BuildableAreaRequest,
    BuildableAreaResponse,
    ProjectBulkDeleteRequest,
    ProjectRecord,
    ProjectUpsertRequest,
)
from pvmath_project_setup import merge_project_data, normalize_legacy_project_data, validate_project_data
from pvmath_supabase import AuthUser, db_hdr, sb_url

router = APIRouter(tags=["projects"])


def _project_base() -> str:
    return f"{sb_url()}/rest/v1/user_projects"


def _parse_geometry(geojson_obj: dict[str, Any] | None) -> BaseGeometry | None:
    if not geojson_obj:
        return None
    obj = geojson_obj
    if obj.get("type") == "Feature":
        obj = obj.get("geometry") or {}
    if obj.get("type") == "FeatureCollection":
        geoms = [shape(feat.get("geometry")) for feat in obj.get("features", []) if feat.get("geometry")]
        if not geoms:
            return None
        return unary_union(geoms)
    if obj.get("type") == "GeometryCollection":
        geoms = [shape(g) for g in obj.get("geometries", []) if g]
        if not geoms:
            return None
        return GeometryCollection(geoms)
    return shape(obj)


def _supabase_error_detail(r: requests.Response, fallback: str) -> str:
    try:
        err = r.json()
        if isinstance(err, dict):
            return str(err.get("message") or err.get("hint") or err.get("details") or fallback)
        if isinstance(err, list) and err:
            first = err[0]
            if isinstance(first, dict):
                return str(first.get("message") or fallback)
    except Exception:
        pass
    return fallback if not r.text else r.text[:500]


def _buildable_area(site_geojson: dict[str, Any], restrictions_geojson: dict[str, Any] | None):
    try:
        site = _parse_geometry(site_geojson)
        restrictions = _parse_geometry(restrictions_geojson)
        if site is None:
            return None, 0.0
        if not site.is_valid:
            site = site.buffer(0)
        if restrictions is not None and not restrictions.is_valid:
            restrictions = restrictions.buffer(0)
        buildable = site if restrictions is None else site.difference(restrictions)
        if buildable.is_empty:
            return None, 0.0
        centroid_lat = float(buildable.centroid.y)
        area_ha = (
            buildable.area * (111320.0**2) * abs(math.cos(math.radians(centroid_lat)))
        ) / 10_000.0
        return buildable.__geo_interface__, round(area_ha, 2)
    except Exception:
        # Never let a malformed boundary block project save/update.
        return None, 0.0


@router.get("/projects", response_model=list[ProjectRecord])
def list_projects(user: AuthUser = Depends(get_current_user)):
    r = requests.get(
        _project_base(),
        params={"user_id": f"eq.{user.user_id}", "select": "*", "order": "updated_at.desc.nullslast,created_at.desc"},
        headers=db_hdr(user.access_token),
        timeout=15,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=_supabase_error_detail(r, "Could not list projects"))
    return r.json()


@router.post("/projects", response_model=ProjectRecord)
def create_project(body: ProjectUpsertRequest, user: AuthUser = Depends(get_current_user)):
    buildable_geo, buildable_ha = _buildable_area(
        body.site_boundary_geojson or {},
        body.restriction_polygons_geojson,
    )
    payload = body.model_dump()
    payload["buildable_area_geojson"] = buildable_geo or payload.get("buildable_area_geojson")
    payload.setdefault("workflow", {})
    payload["workflow"]["buildable_area_ha"] = buildable_ha
    r = requests.post(
        _project_base(),
        json={"user_id": user.user_id, "project_data": payload},
        headers={**db_hdr(user.access_token), "Prefer": "return=representation"},
        timeout=60,
    )
    if r.status_code not in (200, 201):
        raise HTTPException(
            status_code=500,
            detail=_supabase_error_detail(r, "Could not create project"),
        )
    rows = r.json() or []
    return rows[0]


@router.get("/projects/{project_id}", response_model=ProjectRecord)
def get_project(project_id: str, user: AuthUser = Depends(get_current_user)):
    r = requests.get(
        _project_base(),
        params={"id": f"eq.{project_id}", "user_id": f"eq.{user.user_id}", "select": "*", "limit": "1"},
        headers=db_hdr(user.access_token),
        timeout=15,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="Could not load project")
    rows = r.json() or []
    if not rows:
        raise HTTPException(status_code=404, detail="Project not found")
    return rows[0]


@router.post("/projects/validate", response_model=ProjectSetupValidateResponse)
def validate_setup(body: ProjectSetupValidateRequest, _user: AuthUser = Depends(get_current_user)):
    data = normalize_legacy_project_data(body.project_data or {})
    result = validate_project_data(data)
    return result


@router.patch("/projects/{project_id}/partial", response_model=ProjectRecord)
def partial_update_project(
    project_id: str,
    body: ProjectPartialUpdateRequest,
    user: AuthUser = Depends(get_current_user),
):
    existing = get_project(project_id, user)
    current = normalize_legacy_project_data(existing.project_data or {})
    patch = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    merged = merge_project_data(current, patch)
    buildable_geo, buildable_ha = _buildable_area(
        merged.get("site_boundary_geojson") or {},
        merged.get("restriction_polygons_geojson"),
    )
    merged["buildable_area_geojson"] = buildable_geo or merged.get("buildable_area_geojson")
    merged.setdefault("workflow", {})
    merged["workflow"]["buildable_area_ha"] = buildable_ha
    r = requests.patch(
        _project_base(),
        params={"id": f"eq.{project_id}", "user_id": f"eq.{user.user_id}", "select": "*"},
        json={"project_data": merged},
        headers={**db_hdr(user.access_token), "Prefer": "return=representation"},
        timeout=60,
    )
    if r.status_code not in (200, 204):
        raise HTTPException(
            status_code=500,
            detail=_supabase_error_detail(r, "Could not update project"),
        )
    rows = r.json() or []
    if not rows:
        raise HTTPException(status_code=404, detail="Project not found")
    return rows[0]


@router.patch("/projects/{project_id}", response_model=ProjectRecord)
def update_project(
    project_id: str,
    body: ProjectUpsertRequest,
    user: AuthUser = Depends(get_current_user),
):
    existing = get_project(project_id, user)
    current = normalize_legacy_project_data(existing.project_data or {})
    patch = normalize_legacy_project_data(body.model_dump())
    merged = merge_project_data(current, patch)
    buildable_geo, buildable_ha = _buildable_area(
        merged.get("site_boundary_geojson") or {},
        merged.get("restriction_polygons_geojson"),
    )
    merged["buildable_area_geojson"] = buildable_geo or merged.get("buildable_area_geojson")
    merged.setdefault("workflow", {})
    merged["workflow"]["buildable_area_ha"] = buildable_ha
    r = requests.patch(
        _project_base(),
        params={"id": f"eq.{project_id}", "user_id": f"eq.{user.user_id}", "select": "*"},
        json={"project_data": merged},
        headers={**db_hdr(user.access_token), "Prefer": "return=representation"},
        timeout=60,
    )
    if r.status_code not in (200, 204):
        raise HTTPException(
            status_code=500,
            detail=_supabase_error_detail(r, "Could not update project"),
        )
    rows = r.json() or []
    if not rows:
        raise HTTPException(status_code=404, detail="Project not found")
    return rows[0]


@router.post("/projects/bulk-delete")
def bulk_delete_projects(body: ProjectBulkDeleteRequest, user: AuthUser = Depends(get_current_user)):
    ids = list(dict.fromkeys(i.strip() for i in body.ids if i and i.strip()))
    if not ids:
        raise HTTPException(status_code=400, detail="No project ids provided")
    id_filter = ",".join(ids)
    r = requests.delete(
        _project_base(),
        params={
            "id": f"in.({id_filter})",
            "user_id": f"eq.{user.user_id}",
            "select": "id",
        },
        headers={**db_hdr(user.access_token), "Prefer": "return=representation"},
        timeout=60,
    )
    if r.status_code not in (200, 204):
        raise HTTPException(
            status_code=500,
            detail=_supabase_error_detail(r, "Could not delete projects"),
        )
    rows = r.json() if r.status_code == 200 else []
    return {"success": True, "deleted": len(rows) if isinstance(rows, list) else 0}


@router.delete("/projects")
def delete_all_projects(user: AuthUser = Depends(get_current_user)):
    r = requests.delete(
        _project_base(),
        params={"user_id": f"eq.{user.user_id}", "select": "id"},
        headers={**db_hdr(user.access_token), "Prefer": "return=representation"},
        timeout=60,
    )
    if r.status_code not in (200, 204):
        raise HTTPException(
            status_code=500,
            detail=_supabase_error_detail(r, "Could not delete projects"),
        )
    rows = r.json() if r.status_code == 200 else []
    return {"success": True, "deleted": len(rows) if isinstance(rows, list) else 0}


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, user: AuthUser = Depends(get_current_user)):
    r = requests.delete(
        _project_base(),
        params={"id": f"eq.{project_id}", "user_id": f"eq.{user.user_id}"},
        headers=db_hdr(user.access_token),
        timeout=15,
    )
    if r.status_code not in (200, 204):
        raise HTTPException(status_code=500, detail="Could not delete project")
    return {"success": True}


@router.post("/projects/buildable-area", response_model=BuildableAreaResponse)
def preview_buildable_area(body: BuildableAreaRequest, _user: AuthUser = Depends(get_current_user)):
    buildable_geo, buildable_ha = _buildable_area(
        body.site_boundary_geojson,
        body.restriction_polygons_geojson,
    )
    return {
        "buildable_area_geojson": buildable_geo,
        "buildable_area_ha": buildable_ha,
    }
