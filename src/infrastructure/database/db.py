"""Database engine factory and low-level helpers."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine

from src.config.settings import get_settings


def get_engine() -> Engine:
    """Create SQLAlchemy engine from application settings."""

    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True, future=True)
