"""Shared schemas for long-running API jobs."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel


class JobStartResponse(BaseModel):
    job_id: str
    kind: str
    status: Literal["queued", "running", "succeeded", "failed"]


class JobStatusResponse(BaseModel):
    job_id: str
    kind: str
    status: Literal["queued", "running", "succeeded", "failed"]
    created_at: float
    updated_at: float
    error: Optional[str] = None
    result: Any = None
