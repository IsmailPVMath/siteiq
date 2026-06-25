"""Gate analysis endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas.gate import GateAnalyzeRequest, GateAnalyzeResponse
from pvmath_gate.analyze import run_gate_analysis
from pvmath_gate.models import GateRequest

router = APIRouter(tags=["gate"])


@router.post("/gate/analyze", response_model=GateAnalyzeResponse)
def analyze_gate(body: GateAnalyzeRequest):
    """
    Unified gate analysis — one call, full screening payload.

  Workflow (internal engines):
    solar → terrain → flood → regulatory → capacity → yield (4 configs) → layout → BOM
    """
    boundary = None
    if body.boundary:
        boundary = [[p.lat, p.lon] for p in body.boundary]
        if len(boundary) < 3:
            raise HTTPException(status_code=422, detail="boundary requires at least 3 points")

    req = GateRequest(
        project_name=body.project_name,
        lat=body.lat,
        lon=body.lon,
        area_ha=body.area_ha,
        land_use=body.land_use,
        mount_type=body.mount_type,
        country=body.country,
        boundary=boundary,
        run_layout=body.run_layout,
        module_h=body.module_h,
        module_w=body.module_w,
        module_wp=body.module_wp,
        n_portrait=body.n_portrait,
        pitch_m=body.pitch_m,
        setback_m=body.setback_m,
        gcr_1p=body.gcr_1p,
        gcr_2p=body.gcr_2p,
    )

    result = run_gate_analysis(req)
    return GateAnalyzeResponse(
        success=result.success,
        project_name=result.project_name,
        coordinates=result.coordinates,
        solar=result.solar,
        terrain=result.terrain,
        flood=result.flood,
        regulatory=result.regulatory,
        capacity=result.capacity,
        yield_configs=result.yield_configs,
        layout=result.layout,
        bom=result.bom,
        pvmath_score=result.pvmath_score,
        verdict=result.verdict,
        verdict_detail=result.verdict_detail,
        errors=result.errors,
        api_version=result.api_version,
    )
