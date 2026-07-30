from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def _csv_env(name: str, default: str = "") -> list[str]:
    value = os.environ.get(name, default)
    return [part.strip() for part in value.split(",") if part.strip()]


def create_api_app(*, title: str, version: str) -> FastAPI:
    """Create a FastAPI app with environment-driven production defaults.

    OPENCAD_ENABLE_DOCS=false hides OpenAPI/docs routes.
    OPENCAD_CORS_ALLOW_ORIGINS controls cross-origin access as CSV.
    """
    docs_enabled = os.environ.get("OPENCAD_ENABLE_DOCS", "true").lower() == "true"
    app = FastAPI(
        title=title,
        version=version,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    default_origins = "http://127.0.0.1:5173,http://localhost:5173"
    allow_origins = _csv_env("OPENCAD_CORS_ALLOW_ORIGINS", default=default_origins)
    if allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allow_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )

    return app