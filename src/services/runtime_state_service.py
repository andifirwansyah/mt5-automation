"""Service for lightweight runtime key-value state management."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from src.repositories.bot_repository import BotRepository


class RuntimeStateService:
    """Read/write runtime state values persisted in BotRuntimeState.details."""

    def __init__(self, bot_repository: BotRepository, bot_instance_id: uuid.UUID) -> None:
        self.bot_repository = bot_repository
        self.bot_instance_id = bot_instance_id

    def _get_details(self) -> dict[str, Any]:
        state = self.bot_repository.get_runtime_state(self.bot_instance_id)
        if state is None:
            return {}
        return dict(state.details or {})

    def get_state(self, key: str) -> Any:
        details = self._get_details()
        return details.get(key)

    def set_state(self, key: str, value: Any) -> None:
        details = self._get_details()
        details[key] = value
        self.bot_repository.upsert_runtime_state(
            bot_instance_id=self.bot_instance_id,
            is_running=True,
            details=details,
        )
        self.bot_repository.session.commit()

    @staticmethod
    def _candle_key(symbol: str, timeframe: str) -> str:
        return f"last_processed_candle:{symbol}:{timeframe}"

    def get_last_processed_candle(self, symbol: str, timeframe: str) -> datetime | None:
        value = self.get_state(self._candle_key(symbol, timeframe))
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return None

    def set_last_processed_candle(self, symbol: str, timeframe: str, candle_time: datetime) -> None:
        self.set_state(self._candle_key(symbol, timeframe), candle_time.isoformat())
