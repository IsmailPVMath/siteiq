"""Redis + RQ job backend for durable, horizontally scalable heavy work."""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Callable

from api.jobs.serialize import to_builtin
from api.jobs.types import HeavyJob

MAX_ACTIVE_PER_USER = max(1, int(os.environ.get("PVMATH_HEAVY_JOBS_PER_USER", "2")))
MAX_JOBS = max(10, int(os.environ.get("PVMATH_HEAVY_JOB_BACKLOG", "50")))
JOB_TTL_SEC = max(60, int(os.environ.get("PVMATH_HEAVY_JOB_TTL_SEC", "3600")))
RQ_QUEUE_NAME = os.environ.get("PVMATH_RQ_QUEUE", "pvmath-heavy")
JOB_KEY_PREFIX = "pvmath:job:"
USER_ACTIVE_PREFIX = "pvmath:user_active:"
GLOBAL_ACTIVE_KEY = "pvmath:jobs:active_count"


def redis_url() -> str:
    url = (os.environ.get("PVMATH_REDIS_URL") or os.environ.get("REDIS_URL") or "").strip()
    if not url:
        raise RuntimeError("REDIS_URL or PVMATH_REDIS_URL is required for the Redis job backend")
    return url


def _job_key(job_id: str) -> str:
    return f"{JOB_KEY_PREFIX}{job_id}"


def _user_active_key(user_id: str) -> str:
    return f"{USER_ACTIVE_PREFIX}{user_id}"


class RedisJobBackend:
    backend_name = "redis"

    def __init__(self) -> None:
        from redis import Redis

        url = redis_url()
        self._redis = Redis.from_url(url, decode_responses=True)
        self._rq_redis = Redis.from_url(url)

    def _queue(self):
        from rq import Queue

        return Queue(RQ_QUEUE_NAME, connection=self._rq_redis)

    def _load_job(self, job_id: str) -> dict[str, Any] | None:
        raw = self._redis.get(_job_key(job_id))
        if not raw:
            return None
        return json.loads(raw)

    def _save_job(self, record: dict[str, Any]) -> None:
        job_id = record["id"]
        self._redis.set(_job_key(job_id), json.dumps(record), ex=JOB_TTL_SEC)

    def _active_for_user(self, user_id: str) -> int:
        return int(self._redis.scard(_user_active_key(user_id)) or 0)

    def _active_total(self) -> int:
        return int(self._redis.get(GLOBAL_ACTIVE_KEY) or 0)

    def _track_active(self, user_id: str, job_id: str) -> None:
        pipe = self._redis.pipeline()
        pipe.sadd(_user_active_key(user_id), job_id)
        pipe.expire(_user_active_key(user_id), JOB_TTL_SEC)
        pipe.incr(GLOBAL_ACTIVE_KEY)
        pipe.expire(GLOBAL_ACTIVE_KEY, JOB_TTL_SEC)
        pipe.execute()

    def _untrack_active(self, user_id: str, job_id: str) -> None:
        pipe = self._redis.pipeline()
        pipe.srem(_user_active_key(user_id), job_id)
        current = int(self._redis.get(GLOBAL_ACTIVE_KEY) or 0)
        if current > 0:
            pipe.decr(GLOBAL_ACTIVE_KEY)
        pipe.execute()

    def submit(
        self,
        user_id: str,
        kind: str,
        *,
        payload: dict[str, Any] | None = None,
        fn: Callable[[], Any] | None = None,
    ) -> HeavyJob:
        if fn is not None:
            raise RuntimeError("Inline callables are not supported with the Redis job backend")
        if not payload:
            raise ValueError("payload is required for Redis job submission")

        if self._active_total() >= MAX_JOBS:
            raise RuntimeError("Heavy job queue is full. Please try again in a few minutes.")
        if self._active_for_user(user_id) >= MAX_ACTIVE_PER_USER:
            raise RuntimeError("You already have heavy jobs running. Please wait for one to finish.")

        now = time.time()
        job_id = uuid.uuid4().hex
        record = {
            "id": job_id,
            "user_id": user_id,
            "kind": kind,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "result": None,
            "error": None,
            "progress": None,
            "stage": None,
            "payload": payload,
        }
        self._save_job(record)
        self._track_active(user_id, job_id)

        from api.jobs.tasks import run_heavy_job_task

        self._queue().enqueue(
            run_heavy_job_task,
            job_id,
            job_timeout=max(60, int(os.environ.get("PVMATH_HEAVY_JOB_TIMEOUT_SEC", "900"))),
            result_ttl=60,
            failure_ttl=JOB_TTL_SEC,
            job_id=job_id,
        )
        return self._to_heavy_job(record)

    def get(self, user_id: str, job_id: str) -> HeavyJob | None:
        record = self._load_job(job_id)
        if not record or record.get("user_id") != user_id:
            return None
        public = dict(record)
        public.pop("payload", None)
        return self._to_heavy_job(public)

    def run_job(self, job_id: str) -> None:
        """Execute a queued job — called by the RQ worker process."""
        record = self._load_job(job_id)
        if not record:
            raise RuntimeError(f"Job record not found: {job_id}")

        user_id = str(record["user_id"])
        kind = str(record["kind"])
        payload = record.get("payload") or {}

        record["status"] = "running"
        record["updated_at"] = time.time()
        self._save_job(record)

        from api.jobs.handlers import execute

        try:
            result = to_builtin(execute(kind, payload))
            record["result"] = result
            record["status"] = "succeeded"
            record["error"] = None
        except Exception as exc:  # noqa
            record["error"] = str(exc) or exc.__class__.__name__
            record["status"] = "failed"
            raise
        finally:
            record["updated_at"] = time.time()
            self._save_job(record)
            self._untrack_active(user_id, job_id)

    @staticmethod
    def _to_heavy_job(record: dict[str, Any]) -> HeavyJob:
        return HeavyJob(
            id=str(record["id"]),
            user_id=str(record["user_id"]),
            kind=str(record["kind"]),
            status=str(record["status"]),
            created_at=float(record["created_at"]),
            updated_at=float(record["updated_at"]),
            result=record.get("result"),
            error=record.get("error"),
            progress=record.get("progress"),
            stage=record.get("stage"),
        )

    def ping(self) -> bool:
        return bool(self._redis.ping())
