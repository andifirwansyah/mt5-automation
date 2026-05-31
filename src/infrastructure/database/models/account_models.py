"""Account domain ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base, TRADING_SCHEMA


class TradingAccount(Base):
    """Trading account identity and static profile."""

    __tablename__ = "trading_accounts"
    __table_args__ = (
        Index("ix_trading_accounts_account_number", "account_number"),
        Index("ix_trading_accounts_broker_server", "broker_server"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    broker_server: Mapped[str] = mapped_column(String(255), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(16), nullable=False)
    leverage: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class AccountSnapshot(Base):
    """High-frequency account equity/balance snapshots."""

    __tablename__ = "account_snapshots"
    __table_args__ = (
        Index("ix_account_snapshots_account_id_snapshot_time", "account_id", "snapshot_time"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{TRADING_SCHEMA}.trading_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    balance: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    equity: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    margin: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    free_margin: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    margin_level: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    profit: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
