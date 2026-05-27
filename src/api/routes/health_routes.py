"""Health endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from src.config.settings import get_settings
from src.schemas import HealthResponse

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", environment=settings.app_env)
