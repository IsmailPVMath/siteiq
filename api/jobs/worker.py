"""Dedicated heavy-job worker — run: python -m api.jobs.worker"""

from __future__ import annotations

import os
import sys


def main() -> None:
    os.environ.setdefault("PVMATH_JOB_BACKEND", "redis")

    from redis import Redis
    from rq import Queue, Worker

    from api.jobs.redis_backend import RQ_QUEUE_NAME, redis_url

    url = redis_url()
    conn = Redis.from_url(url)
    queue = Queue(RQ_QUEUE_NAME, connection=conn)
    worker_name = os.environ.get("PVMATH_WORKER_NAME", "pvmath-worker")
    worker = Worker([queue], connection=conn, name=worker_name)
    print(f"PVMath worker starting — queue={RQ_QUEUE_NAME} redis={url.split('@')[-1]}")
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
