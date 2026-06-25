"""FastAPI application — PVMath gate analysis API (parallel to Streamlit)."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from api.routers import (
    auth_login,
    boundary,
    gate,
    geocode,
    health,
    me,
    projects,
    reports,
    topoiq,
    yieldiq,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    skip = os.environ.get("PVMATH_API_SKIP_AUTH", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if not skip:
        from pvmath_supabase import sb_key, sb_url

        sb_url()
        sb_key()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="PVMath API",
        description="Gate analysis API — unified site screening (React frontend target).",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    app.openapi_schema = None  # rebuilt below with Bearer auth

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        from fastapi.openapi.utils import get_openapi

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        schema.setdefault("components", {}).setdefault("securitySchemes", {})[
            "BearerAuth"
        ] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Supabase access_token from sign-in",
        }
        for path, methods in schema.get("paths", {}).items():
            if path.startswith("/api/v1/"):
                for op in methods.values():
                    if isinstance(op, dict):
                        op["security"] = [{"BearerAuth": []}]
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi

    origins = os.environ.get(
        "PVMATH_CORS_ORIGINS",
        "http://localhost:5173,http://localhost:3000,"
        "https://siteiq.pvmath.com,https://topoiq.pvmath.com,https://pvmath.com,"
        "https://api.pvmath.com",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", include_in_schema=False)
    def root_redirect():
        return RedirectResponse(url="/api/docs")

    app.include_router(health.router, prefix="/api")
    app.include_router(auth_login.router, prefix="/api/v1")
    app.include_router(geocode.router, prefix="/api/v1")
    app.include_router(boundary.router, prefix="/api/v1")
    app.include_router(reports.router, prefix="/api/v1")
    app.include_router(projects.router, prefix="/api/v1")
    app.include_router(me.router, prefix="/api/v1")
    app.include_router(gate.router, prefix="/api/v1")
    app.include_router(topoiq.router, prefix="/api/v1")
    app.include_router(yieldiq.router, prefix="/api/v1")
    return app


app = create_app()
