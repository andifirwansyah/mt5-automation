"""Repository for market regime tables."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.infrastructure.database.models import MarketRegime


class RegimeRepository:
    """CRUD/query repository for market regime data."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_market_regime(
        self,
        symbol_id: uuid.UUID,
        timeframe_id: uuid.UUID,
        regime: str,
        confidence: float,
        detected_at: datetime,
        features: dict[str, Any] | None = None,
    ) -> MarketRegime:
        entity = MarketRegime(
            symbol_id=symbol_id,
            timeframe_id=timeframe_id,
            regime=regime,
            confidence=confidence,
            detected_at=detected_at,
            features=features or {},
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def get_latest_regime(self, symbol_id: uuid.UUID, timeframe_id: uuid.UUID) -> MarketRegime | None:
        stmt = (
            select(MarketRegime)
            .where(MarketRegime.symbol_id == symbol_id, MarketRegime.timeframe_id == timeframe_id)
            .order_by(MarketRegime.detected_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()
