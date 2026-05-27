"""Performance analytics ORM models."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base, TRADING_SCHEMA


class PerformanceDaily(Base):
    """Daily account-level performance stats."""

    __tablename__ = "performance_daily"
    __table_args__ = (
        UniqueConstraint("account_id", "trade_date", name="uq_performance_daily_account_trade_date"),
        Index("ix_performance_daily_trade_date", "trade_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.trading_accounts.id", ondelete="CASCADE"), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    gross_profit: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    gross_loss: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    net_profit: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    win_rate: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    max_drawdown: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class PerformanceByStrategy(Base):
    """Performance aggregation by strategy and period."""

    __tablename__ = "performance_by_strategy"
    __table_args__ = (
        Index("ix_performance_by_strategy_strategy_period", "strategy_id", "period_start", "period_end"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.strategies.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.trading_accounts.id", ondelete="SET NULL"), nullable=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    win_rate: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    net_profit: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    profit_factor: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class StrategyFeedbackEvent(Base):
    """Feedback signal to improve strategy selection and parameters."""

    __tablename__ = "strategy_feedback_events"
    __table_args__ = (
        Index("ix_strategy_feedback_events_strategy_id_created_at", "strategy_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.strategies.id", ondelete="CASCADE"), nullable=False)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.signals.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
