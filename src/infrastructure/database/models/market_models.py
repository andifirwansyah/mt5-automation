"""Market data and market event ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base, TRADING_SCHEMA


class Symbol(Base):
    """Tradable symbol reference table."""

    __tablename__ = "symbols"
    __table_args__ = (Index("ix_symbols_name", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    asset_class: Mapped[str] = mapped_column(String(32), nullable=False)
    digits: Mapped[int] = mapped_column(Integer, nullable=False)
    point: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class Timeframe(Base):
    """Market timeframe reference table."""

    __tablename__ = "timeframes"
    __table_args__ = (Index("ix_timeframes_code", "code"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Candle(Base):
    """High-volume OHLCV candle table."""

    __tablename__ = "candles"
    __table_args__ = (
        Index("ix_candles_symbol_tf_open_time", "symbol_id", "timeframe_id", "open_time"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.symbols.id", ondelete="CASCADE"), nullable=False)
    timeframe_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.timeframes.id", ondelete="CASCADE"), nullable=False)
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open_price: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    high_price: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    low_price: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    close_price: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    tick_volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    spread: Mapped[int | None] = mapped_column(Integer, nullable=True)
    real_volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    features: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class TickSnapshot(Base):
    """High-volume tick snapshots."""

    __tablename__ = "tick_snapshots"
    __table_args__ = (Index("ix_tick_snapshots_symbol_event_time", "symbol_id", "event_time"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.symbols.id", ondelete="CASCADE"), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bid: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    ask: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    last: Mapped[float | None] = mapped_column(Numeric(20, 10), nullable=True)
    spread: Mapped[float | None] = mapped_column(Numeric(20, 10), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DataQualityCheck(Base):
    """Data quality checks against market data integrity rules."""

    __tablename__ = "data_quality_checks"
    __table_args__ = (
        Index("ix_data_quality_checks_symbol_tf_checked_at", "symbol_id", "timeframe_id", "checked_at"),
        Index("ix_data_quality_checks_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.symbols.id", ondelete="SET NULL"), nullable=True)
    timeframe_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.timeframes.id", ondelete="SET NULL"), nullable=True)
    check_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MarketEvent(Base):
    """Detected market events such as news, session shift, anomaly."""

    __tablename__ = "market_events"
    __table_args__ = (
        Index("ix_market_events_symbol_event_type", "symbol_id", "event_type"),
        Index("ix_market_events_is_active", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.symbols.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class MarketEventFilter(Base):
    """Filter decision for market events in pipeline."""

    __tablename__ = "market_event_filters"
    __table_args__ = (
        Index("ix_market_event_filters_event_id_created_at", "market_event_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{TRADING_SCHEMA}.market_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    filter_name: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
