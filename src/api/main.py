"""Main FastAPI application instance."""

from __future__ import annotations

from fastapi import FastAPI

from src.config.constants import API_V1_PREFIX
from src.config.settings import get_settings


def create_app() -> FastAPI:
    """Create FastAPI app with minimal bootstrap endpoints."""

    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.app_debug)

    @app.get(f"{API_V1_PREFIX}/health", tags=["health"])
    def health_check() -> dict[str, str]:
        return {"status": "ok", "environment": settings.app_env}

    return app


app = create_app()
