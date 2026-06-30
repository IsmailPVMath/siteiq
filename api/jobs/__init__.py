"""Heavy job backends — memory (default) or Redis + RQ when REDIS_URL is set."""

from __future__ import annotations

import os
from typing import Protocol

from api.jobs.types import HeavyJob


class JobBackend(Protocol):
    backend_name: str

    def submit(self, user_id: str, kind: str, *, payload=None, fn=None) -> HeavyJob: ...

    def get(self, user_id: str, job_id: str) -> HeavyJob | None: ...

    def ping(self) -> bool: ...


_backend: JobBackend | None = None


def _redis_configured() -> bool:
    backend = os.environ.get("PVMATH_JOB_BACKEND", "").strip().lower()
    if backend == "memory":
        return False
    if backend == "redis":
        return True
    url = (os.environ.get("PVMATH_REDIS_URL") or os.environ.get("REDIS_URL") or "").strip()
    return bool(url)


def get_backend() -> JobBackend:
    global _backend
    if _backend is None:
        if _redis_configured():
            from api.jobs.redis_backend import RedisJobBackend

            _backend = RedisJobBackend()
        else:
            from api.jobs.memory_backend import MemoryJobBackend

            _backend = MemoryJobBackend()
    return _backend


def reset_backend() -> None:
    """Test helper — force backend re-selection on next get_backend()."""
    global _backend
    _backend = None
