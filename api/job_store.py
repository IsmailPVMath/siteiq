"""Facade for heavy API jobs — memory backend locally, Redis + RQ in production."""

from __future__ import annotations

from typing import Any, Callable

from api.jobs import get_backend
from api.jobs.types import HeavyJob


def submit_heavy_job(
    user_id: str,
    kind: str,
    fn: Callable[[], Any] | None = None,
    *,
    payload: dict[str, Any] | None = None,
) -> HeavyJob:
    """Queue a heavy job. Prefer ``payload`` for Redis; ``fn`` works in memory mode."""
    return get_backend().submit(user_id, kind, payload=payload, fn=fn)


def get_heavy_job(user_id: str, job_id: str) -> HeavyJob | None:
    return get_backend().get(user_id, job_id)


def job_backend_name() -> str:
    return get_backend().backend_name
