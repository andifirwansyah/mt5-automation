"""Trade cooldown guard engine."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from src.config.settings import AppSettings, get_settings
from src.domain.enums import ValidationStatus
from src.domain.models.validation_result import ValidationResult
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories.signal_repository import SignalRepository


class TradeCooldownGuard(PipelineStep):
    """Prevent repeated entries on the same symbol/timeframe too quickly."""

    @property
    def name(self) -> str:
        return "TradeCooldownGuard"

    def __init__(self, signal_repository: SignalRepository, settings: AppSettings | Any | None = None) -> None:
        self.signal_repository = signal_repository
        self.settings = settings or get_settings()

    @staticmethod
    def _as_uuid(value: object) -> Any | None:
        import uuid

        if isinstance(value, uuid.UUID):
            return value
        if isinstance(value, str) and value:
            try:
                return uuid.UUID(value)
            except ValueError:
                return None
        return None

    def run(self, context: TradingContext) -> TradingContext:
        if context.signal_contract is None:
            context.reject("TRADE_COOLDOWN_FAILED", {"message": "signal_contract missing"})
            return context

        cooldown_minutes = int(getattr(self.settings, "trade_cooldown_minutes", 10))
        if cooldown_minutes <= 0:
            context.trade_cooldown_result = ValidationResult(
                status=ValidationStatus.PASSED,
                validator_name=self.name,
                details={"message": "Cooldown disabled", "cooldown_minutes": cooldown_minutes},
            )
            return context

        ingestion = context.ingestion_result or {}
        symbol_id = self._as_uuid(ingestion.get("symbol_id"))
        timeframe_id = self._as_uuid((ingestion.get("timeframe_ids") or {}).get(context.timeframe))
        signal_id = self._as_uuid(context.signal_contract.metadata.get("signal_id"))
        if symbol_id is None or timeframe_id is None:
            context.reject("TRADE_COOLDOWN_FAILED", {"message": "symbol/timeframe references missing"})
            return context

        since = context.candle_time - timedelta(minutes=cooldown_minutes)
        recent_count = self.signal_repository.count_recent_signals(
            symbol_id=symbol_id,
            timeframe_id=timeframe_id,
            since=since,
            exclude_signal_id=signal_id,
        )
        details = {"cooldown_minutes": cooldown_minutes, "since": since.isoformat(), "recent_signal_count": recent_count}
        if recent_count > 0:
            context.trade_cooldown_result = ValidationResult(
                status=ValidationStatus.REJECTED,
                reason="TRADE_COOLDOWN_ACTIVE",
                validator_name=self.name,
                details=details,
            )
            context.reject("TRADE_COOLDOWN_ACTIVE", details)
            return context

        context.trade_cooldown_result = ValidationResult(status=ValidationStatus.PASSED, validator_name=self.name, details=details)
        return context
