"""FastAPI application — PVMath gate analysis API (parallel to Streamlit)."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import gate, health


@asynccontextmanager
async def lifespan(app: FastAPI):
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

    app.include_router(health.router, prefix="/api")
    app.include_router(gate.router, prefix="/api/v1")
    return app


app = create_app()
