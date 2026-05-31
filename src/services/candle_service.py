"""Service for candle persistence and duplicate checks."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from src.infrastructure.database.models import Candle
from src.repositories.market_repository import MarketRepository


class CandleService:
    """Facade for candle storage/read operations."""

    def __init__(self, market_repository: MarketRepository) -> None:
        self.market_repository = market_repository

    def save_candles(self, candles: list[dict[str, Any]]) -> list[Candle]:
        entities = self.market_repository.bulk_upsert_candles(candles)
        self.market_repository.session.commit()
        return entities

    def get_latest_candles(self, symbol_id: uuid.UUID, timeframe_id: uuid.UUID, limit: int = 200) -> list[Candle]:
        return self.market_repository.get_latest_candles(symbol_id=symbol_id, timeframe_id=timeframe_id, limit=limit)

    def detect_duplicate(self, symbol_id: uuid.UUID, timeframe_id: uuid.UUID, open_time: datetime) -> bool:
        latest = self.market_repository.get_latest_candles(symbol_id=symbol_id, timeframe_id=timeframe_id, limit=1)
        if not latest:
            return False
        return latest[0].open_time == open_time
