"""RQ worker task entrypoints — must remain importable at module top level."""

from __future__ import annotations


def run_heavy_job_task(job_id: str) -> None:
    from api.jobs.redis_backend import RedisJobBackend

    RedisJobBackend().run_job(job_id)
