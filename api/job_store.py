"""Small in-process job runner for heavy API work.

This is intentionally simple: it keeps long-running terrain/layout work out of
the HTTP request lifecycle and limits concurrent heavy jobs. A future Redis/RQ
or Celery worker can keep the same start/status API shape.
"""

from __future__ import annotations

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable


JobStatus = str

MAX_WORKERS = max(1, int(os.environ.get("PVMATH_HEAVY_JOB_WORKERS", "1")))
MAX_ACTIVE_PER_USER = max(1, int(os.environ.get("PVMATH_HEAVY_JOBS_PER_USER", "2")))
MAX_JOBS = max(10, int(os.environ.get("PVMATH_HEAVY_JOB_BACKLOG", "50")))
JOB_TTL_SEC = max(60, int(os.environ.get("PVMATH_HEAVY_JOB_TTL_SEC", "3600")))

_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="pvmath-heavy")
_lock = Lock()
_jobs: dict[str, "HeavyJob"] = {}


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

    def public(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "kind": self.kind,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
            "result": self.result,
        }


def _to_builtin(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {str(k): _to_builtin(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_builtin(v) for v in value]
    return value


def _prune_locked(now: float) -> None:
    expired = [
        job_id
        for job_id, job in _jobs.items()
        if job.status in {"succeeded", "failed"} and now - job.updated_at > JOB_TTL_SEC
    ]
    for job_id in expired:
        _jobs.pop(job_id, None)


def _active_for_user_locked(user_id: str) -> int:
    return sum(
        1
        for job in _jobs.values()
        if job.user_id == user_id and job.status in {"queued", "running"}
    )


def submit_heavy_job(user_id: str, kind: str, fn: Callable[[], Any]) -> HeavyJob:
    now = time.time()
    with _lock:
        _prune_locked(now)
        if len(_jobs) >= MAX_JOBS:
            raise RuntimeError("Heavy job queue is full. Please try again in a few minutes.")
        if _active_for_user_locked(user_id) >= MAX_ACTIVE_PER_USER:
            raise RuntimeError("You already have heavy jobs running. Please wait for one to finish.")
        job = HeavyJob(id=uuid.uuid4().hex, user_id=user_id, kind=kind)
        _jobs[job.id] = job

    def run() -> None:
        with _lock:
            job.status = "running"
            job.updated_at = time.time()
        try:
            result = _to_builtin(fn())
            with _lock:
                job.result = result
                job.status = "succeeded"
                job.updated_at = time.time()
        except Exception as exc:  # noqa: BLE001 - surfaced to API status endpoint
            with _lock:
                job.error = str(exc) or exc.__class__.__name__
                job.status = "failed"
                job.updated_at = time.time()

    _executor.submit(run)
    return job


def get_heavy_job(user_id: str, job_id: str) -> HeavyJob | None:
    with _lock:
        job = _jobs.get(job_id)
        if not job or job.user_id != user_id:
            return None
        return HeavyJob(**job.__dict__)
