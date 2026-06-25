"""Pydantic schemas for YieldIQ API."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from pvmath_yield import DEFAULT_GCR_1P, DEFAULT_OTHER_LOSS_PCT, DEFAULT_SOILING_PCT


class YieldIQAnalyzeRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    mount_type: str = Field(default="Fixed Tilt")
    gcr_1p: float = Field(default=DEFAULT_GCR_1P, gt=0, le=1)
    gcr_2p: float = Field(default=0.42, gt=0, le=1)
    soiling_loss: float = Field(default=DEFAULT_SOILING_PCT, ge=0, le=30)
    other_loss: float = Field(default=DEFAULT_OTHER_LOSS_PCT, ge=0, le=30)


class YieldIQAnalyzeResponse(BaseModel):
    lat: float
    lon: float
    mount_type: str
    raddatabase: Optional[str] = None
    configs: Dict[str, Dict[str, Any]]
    cross_ref_bundle: Dict[str, Optional[float]]
    disclosure: str
