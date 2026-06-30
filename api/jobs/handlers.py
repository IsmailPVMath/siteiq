"""Dispatch heavy jobs by kind — import router helpers lazily to avoid cycles."""

from __future__ import annotations

from typing import Any, Callable


HandlerFn = Callable[[dict[str, Any]], Any]

_HANDLERS: dict[str, HandlerFn] = {}


def register(kind: str, fn: HandlerFn) -> None:
    _HANDLERS[kind] = fn


def execute(kind: str, payload: dict[str, Any]) -> Any:
    if kind not in _HANDLERS:
        raise ValueError(f"Unknown job kind: {kind}")
    return _HANDLERS[kind](payload)


def _terrainiq_analyze(payload: dict[str, Any]) -> Any:
    from api.routers.terrainiq import _run_analysis_response
    from api.schemas.terrainiq import TerrainIQAnalyzeRequest

    body = TerrainIQAnalyzeRequest.model_validate(payload)
    return _run_analysis_response(body)


def _workflow_terrain_mesh(payload: dict[str, Any]) -> Any:
    from api.routers.workflow import _build_terrain_mesh_response
    from api.schemas.workflow import WorkflowTerrainMeshRequest

    body = WorkflowTerrainMeshRequest.model_validate(payload)
    return _build_terrain_mesh_response(body)


def _workflow_layout_sweep(payload: dict[str, Any]) -> Any:
    from api.routers.workflow import _build_layout_sweep_response
    from api.schemas.workflow import WorkflowLayoutSweepRequest

    body = WorkflowLayoutSweepRequest.model_validate(payload)
    return _build_layout_sweep_response(body)


register("terrainiq.analyze", _terrainiq_analyze)
register("workflow.terrain_mesh", _workflow_terrain_mesh)
register("workflow.layout_sweep", _workflow_layout_sweep)
