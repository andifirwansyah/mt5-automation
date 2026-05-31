"""Risk and simulation ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base, TRADING_SCHEMA


class RiskAssessment(Base):
    """Risk engine output for a signal."""

    __tablename__ = "risk_assessments"
    __table_args__ = (
        Index("ix_risk_assessments_signal_id", "signal_id"),
        Index("ix_risk_assessments_passed", "passed"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.signals.id", ondelete="CASCADE"), nullable=False)
    risk_per_trade_pct: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    max_daily_loss_pct: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    position_size_lot: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    stop_loss_pips: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    take_profit_pips: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    risk_reward_ratio: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PreTradeSimulation(Base):
    """Pre-trade simulation output before execution gate."""

    __tablename__ = "pre_trade_simulations"
    __table_args__ = (
        Index("ix_pre_trade_simulations_signal_id", "signal_id"),
        Index("ix_pre_trade_simulations_passed", "passed"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.signals.id", ondelete="CASCADE"), nullable=False)
    expected_profit: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    expected_drawdown: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    slippage_estimate: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    simulated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
