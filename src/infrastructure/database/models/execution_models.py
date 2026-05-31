"""Execution-related ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base, TRADING_SCHEMA


class BrokerHealthCheck(Base):
    """Broker/MT5 health snapshots before execution."""

    __tablename__ = "broker_health_checks"
    __table_args__ = (
        Index("ix_broker_health_checks_checked_at", "checked_at"),
        Index("ix_broker_health_checks_is_healthy", "is_healthy"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.symbols.id", ondelete="SET NULL"), nullable=True)
    is_connected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_trade_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_healthy: Mapped[bool] = mapped_column(Boolean, nullable=False)
    spread: Mapped[float | None] = mapped_column(Numeric(20, 10), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ExecutionDecision(Base):
    """Execution gate final decision."""

    __tablename__ = "execution_decisions"
    __table_args__ = (
        Index("ix_execution_decisions_signal_id", "signal_id"),
        Index("ix_execution_decisions_trace_id", "trace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.signals.id", ondelete="CASCADE"), nullable=False)
    trace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ApprovalRequest(Base):
    """Approval flow state for execution request."""

    __tablename__ = "approval_requests"
    __table_args__ = (
        Index("ix_approval_requests_execution_decision_id", "execution_decision_id"),
        Index("ix_approval_requests_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{TRADING_SCHEMA}.execution_decisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ExecutionOrder(Base):
    """Final broker execution order records."""

    __tablename__ = "execution_orders"
    __table_args__ = (
        Index("ix_execution_orders_signal_id", "signal_id"),
        Index("ix_execution_orders_mt5_order_ticket", "mt5_order_ticket"),
        Index("ix_execution_orders_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.signals.id", ondelete="CASCADE"), nullable=False)
    execution_decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.execution_decisions.id", ondelete="SET NULL"), nullable=True)
    symbol_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.symbols.id", ondelete="CASCADE"), nullable=False)
    mt5_order_ticket: Mapped[int | None] = mapped_column(BigInteger, nullable=True, unique=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(32), nullable=False)
    volume_lot: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    requested_price: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    stop_loss: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    take_profit: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    deviation: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    broker_response: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
