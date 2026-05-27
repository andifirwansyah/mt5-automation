"""Market event filter engine."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any

from src.domain.enums import ValidationStatus
from src.domain.models.validation_result import ValidationResult
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories.market_repository import MarketRepository


class MarketEventFilter(PipelineStep):
    """Filter trading based on session rules and high-impact events."""

    @property
    def name(self) -> str:
        return "MarketEventFilter"

    def __init__(self, market_repository: MarketRepository, high_impact_window_minutes: int = 30) -> None:
        self.market_repository = market_repository
        self.high_impact_window_minutes = high_impact_window_minutes

    @staticmethod
    def _is_trading_session(candle_time: datetime) -> bool:
        t = candle_time.astimezone(timezone.utc).time()
        # Basic guard: avoid very-low-liquidity rollover window around 22:00-23:00 UTC
        return not (time(22, 0) <= t <= time(23, 0))

    def run(self, context: TradingContext) -> TradingContext:
        now = context.candle_time if context.candle_time.tzinfo else context.candle_time.replace(tzinfo=timezone.utc)
        window_start = now - timedelta(minutes=self.high_impact_window_minutes)
        window_end = now + timedelta(minutes=self.high_impact_window_minutes)

        if not self._is_trading_session(now):
            result = ValidationResult(
                status=ValidationStatus.REJECTED,
                reason="SESSION_FILTER_BLOCKED",
                validator_name="MarketEventFilter",
                details={"message": "Outside allowed trading session"},
            )
            context.market_event_result = result
            self.market_repository.create_market_event_filter(
                filter_name="SESSION_FILTER",
                action="BLOCK",
                reason="SESSION_FILTER_BLOCKED",
                details=result.details,
            )
            self.market_repository.session.commit()
            context.reject("SESSION_FILTER_BLOCKED", result.details)
            return context

        symbol_id = (context.ingestion_result or {}).get("symbol_id")
        events = self.market_repository.get_active_market_events(
            window_start=window_start,
            window_end=window_end,
            symbol_id=symbol_id,
            severity="HIGH",
        )

        if events:
            details = {
                "message": "High impact event in restricted window",
                "events": [
                    {
                        "event_id": str(e.id),
                        "event_type": e.event_type,
                        "title": e.title,
                        "starts_at": e.starts_at.isoformat() if e.starts_at else None,
                        "ends_at": e.ends_at.isoformat() if e.ends_at else None,
                    }
                    for e in events
                ],
            }
            context.market_event_result = ValidationResult(
                status=ValidationStatus.REJECTED,
                reason="MARKET_EVENT_BLOCKED",
                validator_name="MarketEventFilter",
                details=details,
            )
            for e in events:
                self.market_repository.create_market_event_filter(
                    filter_name="MARKET_EVENT_FILTER",
                    action="BLOCK",
                    market_event_id=e.id,
                    reason="MARKET_EVENT_BLOCKED",
                    details=details,
                )
            self.market_repository.session.commit()
            context.reject("MARKET_EVENT_BLOCKED", details)
            return context

        details = {"message": "No blocking market event found; default allow."}
        context.market_event_result = ValidationResult(
            status=ValidationStatus.PASSED,
            reason=None,
            validator_name="MarketEventFilter",
            details=details,
        )
        self.market_repository.create_market_event_filter(
            filter_name="MARKET_EVENT_FILTER",
            action="ALLOW",
            reason="NO_BLOCKING_EVENT",
            details=details,
        )
        self.market_repository.session.commit()
        return context
