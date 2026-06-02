"""Data quality guard engine for market data validation checks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.config.settings import AppSettings, get_settings
from src.domain.enums import ValidationStatus
from src.domain.models.validation_result import ValidationResult
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories.market_repository import MarketRepository
from src.services.candle_service import CandleService


class DataQualityGuard(PipelineStep):
    """Validate market data integrity before strategy and execution phases."""

    @property
    def name(self) -> str:
        return "DataQualityGuard"

    def __init__(
        self,
        market_repository: MarketRepository,
        candle_service: CandleService,
        max_spread: float | None = None,
        settings: AppSettings | None = None,
    ) -> None:
        self.market_repository = market_repository
        self.candle_service = candle_service
        self.max_spread = max_spread
        self.settings = settings or get_settings()

    @staticmethod
    def _timeframe_to_minutes(timeframe: str) -> int:
        if timeframe.startswith("M"):
            return int(timeframe[1:])
        if timeframe.startswith("H"):
            return int(timeframe[1:]) * 60
        if timeframe == "D1":
            return 1440
        return 1

    def _record_check(
        self,
        status: str,
        check_name: str,
        checked_at: datetime,
        details: dict[str, Any],
        symbol_id: str | None,
        timeframe_id: str | None,
        rejection_reason: str | None = None,
    ) -> None:
        self.market_repository.create_data_quality_check(
            symbol_id=symbol_id,
            timeframe_id=timeframe_id,
            check_name=check_name,
            status=status,
            rejection_reason=rejection_reason,
            details=details,
            checked_at=checked_at,
        )

    def run(self, context: TradingContext) -> TradingContext:
        issues: list[dict[str, Any]] = []
        checked_at = datetime.now(timezone.utc)
        max_spread = float(self.max_spread if self.max_spread is not None else self.settings.max_spread)

        ingestion = context.ingestion_result or {}
        symbol_id = ingestion.get("symbol_id")
        timeframe_id = (ingestion.get("timeframe_ids") or {}).get(context.timeframe)
        snapshot = context.market_snapshot

        if snapshot is None:
            issues.append({"check": "CANDLE_EMPTY", "message": "market_snapshot is None"})
        else:
            if snapshot.high_price < snapshot.low_price:
                issues.append({"check": "OHLC_INVALID", "message": "high_price < low_price"})
            if snapshot.close_price > snapshot.high_price or snapshot.close_price < snapshot.low_price:
                issues.append({"check": "OHLC_INVALID", "message": "close outside range"})
            if snapshot.open_price > snapshot.high_price or snapshot.open_price < snapshot.low_price:
                issues.append({"check": "OHLC_INVALID", "message": "open outside range"})

            spread = snapshot.spread
            if spread is not None and float(spread) > max_spread:
                issues.append({"check": "SPREAD_ABNORMAL", "message": f"spread={spread} > max_spread={max_spread}"})

        if ingestion.get("duplicate_entry_candle"):
            issues.append({"check": "DUPLICATE_CANDLE", "message": "entry candle duplicated"})

        if symbol_id and timeframe_id:
            latest_two = self.candle_service.get_latest_candles(symbol_id=symbol_id, timeframe_id=timeframe_id, limit=2)
            if len(latest_two) == 2:
                c0 = latest_two[0].open_time
                c1 = latest_two[1].open_time
                delta = abs(c0 - c1)
                expected = timedelta(minutes=self._timeframe_to_minutes(context.timeframe))
                if delta > (expected * 2):
                    issues.append(
                        {
                            "check": "MISSING_CANDLE_SIMPLE",
                            "message": f"gap={delta} expected<={expected * 2}",
                        }
                    )

        if issues:
            for issue in issues:
                self._record_check(
                    status="REJECTED",
                    check_name=issue["check"],
                    checked_at=checked_at,
                    details=issue,
                    symbol_id=symbol_id,
                    timeframe_id=timeframe_id,
                    rejection_reason="DATA_QUALITY_FAILED",
                )

            self.market_repository.session.commit()
            context.data_quality_result = ValidationResult(
                status=ValidationStatus.REJECTED,
                reason="DATA_QUALITY_FAILED",
                validator_name="DataQualityGuard",
                details={"issues": issues},
            )
            context.reject(reason="DATA_QUALITY_FAILED", details={"issues": issues})
            return context

        self._record_check(
            status="PASSED",
            check_name="DATA_QUALITY_SUMMARY",
            checked_at=checked_at,
            details={"message": "All checks passed"},
            symbol_id=symbol_id,
            timeframe_id=timeframe_id,
        )
        self.market_repository.session.commit()

        context.data_quality_result = ValidationResult(
            status=ValidationStatus.PASSED,
            reason=None,
            validator_name="DataQualityGuard",
            details={"issues": []},
        )
        return context
