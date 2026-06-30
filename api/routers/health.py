import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.jobs import get_backend

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": "pvmath-api",
        "version": "0.1.0",
        "job_backend": get_backend().backend_name,
    }


@router.get("/health/ready")
def ready():
    """Readiness probe — verifies job backend connectivity."""
    backend = get_backend()
    checks = {
        "api": True,
        "jobs": backend.backend_name,
    }
    if backend.backend_name == "redis":
        try:
            checks["redis"] = backend.ping()
        except Exception as exc:  # noqa: BLE001
            checks["redis"] = False
            checks["redis_error"] = str(exc)
        if not checks["redis"]:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "checks": checks},
            )
    skip_auth = os.environ.get("PVMATH_API_SKIP_AUTH", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if not skip_auth:
        try:
            from pvmath_supabase import sb_key, sb_url

            sb_url()
            sb_key()
            checks["supabase_config"] = True
        except Exception as exc:  # noqa: BLE001
            checks["supabase_config"] = False
            checks["supabase_error"] = str(exc)
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "checks": checks},
            )
    return {"status": "ready", "checks": checks}


@router.get("/")
def root():
    return {"service": "pvmath-api", "health": "/api/health", "docs": "/api/docs"}
