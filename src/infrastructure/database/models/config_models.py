"""Runtime configuration ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base


class RuntimeConfig(Base):
    """DB-backed runtime-editable configuration values."""

    __tablename__ = "runtime_configs"
    __table_args__ = (
        Index("ix_runtime_configs_config_key", "config_key", unique=True),
        Index("ix_runtime_configs_is_active_updated_at", "is_active", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    config_value: Mapped[object] = mapped_column(JSONB, nullable=False)
    value_type: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    update_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
