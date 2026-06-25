from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok", "service": "pvmath-api", "version": "0.1.0"}


@router.get("/")
def root():
    return {"service": "pvmath-api", "health": "/api/health", "docs": "/api/docs"}
