"""Position ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base, TRADING_SCHEMA


class Position(Base):
    """Live and historical trading positions."""

    __tablename__ = "positions"
    __table_args__ = (
        Index("ix_positions_account_id_status", "account_id", "status"),
        Index("ix_positions_symbol_id_status", "symbol_id", "status"),
        Index("ix_positions_mt5_position_ticket", "mt5_position_ticket"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.execution_orders.id", ondelete="SET NULL"), nullable=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.trading_accounts.id", ondelete="CASCADE"), nullable=False)
    symbol_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.symbols.id", ondelete="CASCADE"), nullable=False)
    mt5_position_ticket: Mapped[int | None] = mapped_column(BigInteger, nullable=True, unique=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    volume_lot: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    entry_price: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    stop_loss: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    take_profit: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    close_price: Mapped[float | None] = mapped_column(Numeric(20, 10), nullable=True)
    profit: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class PositionSnapshot(Base):
    """High-volume per-position snapshot table."""

    __tablename__ = "position_snapshots"
    __table_args__ = (Index("ix_position_snapshots_position_id_snapshot_time", "position_id", "snapshot_time"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    position_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.positions.id", ondelete="CASCADE"), nullable=False)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_price: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    unrealized_profit: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    swap: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    commission: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
