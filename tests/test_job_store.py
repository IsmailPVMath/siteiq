"""Tests for heavy job backends."""

from __future__ import annotations

import os
import time
import unittest
from unittest import mock

from api.jobs import get_backend, reset_backend
from api.jobs.handlers import execute, register
from api.jobs.memory_backend import MemoryJobBackend
from api.job_store import get_heavy_job, submit_heavy_job


class MemoryJobBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["PVMATH_JOB_BACKEND"] = "memory"
        reset_backend()

    def tearDown(self) -> None:
        reset_backend()

    def test_submit_and_complete_payload_job(self) -> None:
        register("test.echo", lambda payload: {"value": payload["x"] * 2})
        job = submit_heavy_job("user-1", "test.echo", payload={"x": 21})
        deadline = time.time() + 5
        status = None
        while time.time() < deadline:
            current = get_heavy_job("user-1", job.id)
            if current and current.status in {"succeeded", "failed"}:
                status = current
                break
            time.sleep(0.05)
        self.assertIsNotNone(status)
        assert status is not None
        self.assertEqual(status.status, "succeeded")
        self.assertEqual(status.result, {"value": 42})

    def test_memory_backend_uses_inline_fn(self) -> None:
        job = submit_heavy_job("user-2", "test.inline", fn=lambda: {"ok": True})
        deadline = time.time() + 5
        while time.time() < deadline:
            current = get_heavy_job("user-2", job.id)
            if current and current.status == "succeeded":
                self.assertEqual(current.result, {"ok": True})
                return
            time.sleep(0.05)
        self.fail("job did not succeed in time")


class JobBackendSelectionTests(unittest.TestCase):
    def tearDown(self) -> None:
        reset_backend()

    def test_defaults_to_memory_without_redis(self) -> None:
        with mock.patch.dict(os.environ, {"PVMATH_JOB_BACKEND": "memory", "REDIS_URL": ""}, clear=False):
            reset_backend()
            self.assertEqual(get_backend().backend_name, "memory")

    def test_selects_redis_when_url_present(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"PVMATH_JOB_BACKEND": "", "REDIS_URL": "redis://localhost:6379/0"},
            clear=False,
        ):
            reset_backend()
            with mock.patch("api.jobs.redis_backend.RedisJobBackend.__init__", return_value=None):
                backend = get_backend()
            self.assertEqual(backend.backend_name, "redis")


class HandlerRegistryTests(unittest.TestCase):
    def test_unknown_kind_raises(self) -> None:
        with self.assertRaises(ValueError):
            execute("missing.kind", {})


if __name__ == "__main__":
    unittest.main()
