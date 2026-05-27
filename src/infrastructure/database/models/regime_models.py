"""Market regime ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base, TRADING_SCHEMA


class MarketRegime(Base):
    """Detected market regime classification."""

    __tablename__ = "market_regimes"
    __table_args__ = (
        Index("ix_market_regimes_symbol_tf_detected_at", "symbol_id", "timeframe_id", "detected_at"),
        Index("ix_market_regimes_regime", "regime"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.symbols.id", ondelete="CASCADE"), nullable=False)
    timeframe_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{TRADING_SCHEMA}.timeframes.id", ondelete="CASCADE"), nullable=False)
    regime: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    features: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
