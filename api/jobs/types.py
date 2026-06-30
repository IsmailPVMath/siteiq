"""Shared types for heavy job execution."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


JobStatus = str


@dataclass
class HeavyJob:
    id: str
    user_id: str
    kind: str
    status: JobStatus = "queued"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    result: Any = None
    error: str | None = None
    progress: float | None = None
    stage: str | None = None

    def public(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "job_id": self.id,
            "kind": self.kind,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
            "result": self.result,
        }
        if self.progress is not None:
            payload["progress"] = self.progress
        if self.stage is not None:
            payload["stage"] = self.stage
        return payload
