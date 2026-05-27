"""SQLAlchemy declarative base configuration."""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


TRADING_SCHEMA: str = "trading"

metadata_obj = MetaData(schema=TRADING_SCHEMA)


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    metadata = metadata_obj
