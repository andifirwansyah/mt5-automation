"""Strategy ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base, TRADING_SCHEMA


class Strategy(Base):
    """Strategy catalog."""

    __tablename__ = "strategies"
    __table_args__ = (Index("ix_strategies_code", "code"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class StrategyConfig(Base):
    """Per strategy configuration entries."""

    __tablename__ = "strategy_configs"
    __table_args__ = (
        Index("ix_strategy_configs_strategy_id", "strategy_id"),
        Index("ix_strategy_configs_symbol_tf", "symbol_id", "timeframe_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.strategies.id", ondelete="CASCADE"), nullable=False)
    symbol_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.symbols.id", ondelete="SET NULL"), nullable=True)
    timeframe_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.timeframes.id", ondelete="SET NULL"), nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class StrategySelection(Base):
    """Strategy selector output for each trace/event."""

    __tablename__ = "strategy_selections"
    __table_args__ = (
        Index("ix_strategy_selections_trace_id", "trace_id"),
        Index("ix_strategy_selections_symbol_tf_created_at", "symbol_id", "timeframe_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    symbol_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.symbols.id", ondelete="CASCADE"), nullable=False)
    timeframe_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.timeframes.id", ondelete="CASCADE"), nullable=False)
    regime_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.market_regimes.id", ondelete="SET NULL"), nullable=True)
    strategy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.strategies.id", ondelete="RESTRICT"), nullable=False)
    score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
