"""In-process job runner — default when Redis is not configured."""

from __future__ import annotations

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any, Callable

from api.jobs.handlers import execute
from api.jobs.serialize import to_builtin
from api.jobs.types import HeavyJob

MAX_WORKERS = max(1, int(os.environ.get("PVMATH_HEAVY_JOB_WORKERS", "1")))
MAX_ACTIVE_PER_USER = max(1, int(os.environ.get("PVMATH_HEAVY_JOBS_PER_USER", "2")))
MAX_JOBS = max(10, int(os.environ.get("PVMATH_HEAVY_JOB_BACKLOG", "50")))
JOB_TTL_SEC = max(60, int(os.environ.get("PVMATH_HEAVY_JOB_TTL_SEC", "3600")))

_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="pvmath-heavy")
_lock = Lock()
_jobs: dict[str, HeavyJob] = {}


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


def _active_total_locked() -> int:
    return sum(1 for job in _jobs.values() if job.status in {"queued", "running"})


class MemoryJobBackend:
    backend_name = "memory"

    def submit(
        self,
        user_id: str,
        kind: str,
        *,
        payload: dict[str, Any] | None = None,
        fn: Callable[[], Any] | None = None,
    ) -> HeavyJob:
        if payload is None and fn is None:
            raise ValueError("payload or fn is required")
        now = time.time()
        with _lock:
            _prune_locked(now)
            if _active_total_locked() >= MAX_JOBS:
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
                if fn is not None:
                    result = fn()
                else:
                    result = execute(kind, payload or {})
                result = to_builtin(result)
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

    def get(self, user_id: str, job_id: str) -> HeavyJob | None:
        with _lock:
            job = _jobs.get(job_id)
            if not job or job.user_id != user_id:
                return None
            return HeavyJob(**job.__dict__)

    def ping(self) -> bool:
        return True
