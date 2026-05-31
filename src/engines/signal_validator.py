"""Signal validator engine."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from src.config.settings import AppSettings, get_settings
from src.domain.enums import MarketRegimeType, SignalDirection, ValidationStatus
from src.domain.models.validation_result import ValidationResult
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories.position_repository import PositionRepository
from src.repositories.signal_repository import SignalRepository


class SignalValidator(PipelineStep):
    """Validate normalized signal contract before edge/risk stages."""

    @property
    def name(self) -> str:
        return "SignalValidator"

    def __init__(self, signal_repository: SignalRepository, position_repository: PositionRepository, settings: AppSettings | None = None) -> None:
        self.signal_repository = signal_repository
        self.position_repository = position_repository
        self.settings = settings or get_settings()

    @staticmethod
    def _as_uuid(value: object) -> uuid.UUID | None:
        if isinstance(value, uuid.UUID):
            return value
        if isinstance(value, str) and value:
            try:
                return uuid.UUID(value)
            except ValueError:
                return None
        return None

    def _is_regime_strategy_compatible(self, regime: MarketRegimeType, strategy_code: str) -> bool:
        code = strategy_code.upper()
        if regime in (MarketRegimeType.TRENDING_BULLISH, MarketRegimeType.TRENDING_BEARISH):
            return "TREND" in code
        if regime == MarketRegimeType.RANGING:
            return "REVERSION" in code or "RANGE" in code
        if regime == MarketRegimeType.HIGH_VOLATILITY:
            return "BREAKOUT" in code
        if regime == MarketRegimeType.CHOPPY:
            return False
        return True

    def run(self, context: TradingContext) -> TradingContext:
        if context.signal_contract is None:
            context.reject("SIGNAL_VALIDATION_FAILED", {"message": "signal_contract missing"})
            return context

        contract = context.signal_contract
        issues: list[dict[str, Any]] = []

        if contract.direction not in (SignalDirection.BUY, SignalDirection.SELL):
            issues.append({"check": "SIDE_VALID", "message": f"Invalid side={contract.direction}"})

        if contract.entry_price <= 0:
            issues.append({"check": "ENTRY_PRICE_VALID", "message": "entry_price must be > 0"})

        ingestion = context.ingestion_result or {}
        symbol_id = self._as_uuid(ingestion.get("symbol_id"))
        timeframe_id = self._as_uuid((ingestion.get("timeframe_ids") or {}).get(context.timeframe))
        signal_id = self._as_uuid(contract.metadata.get("signal_id"))

        if symbol_id and timeframe_id:
            duplicate_count = self.signal_repository.count_signals_by_candle(
                symbol_id=symbol_id,
                timeframe_id=timeframe_id,
                signal_time=contract.generated_at,
                exclude_signal_id=signal_id,
            )
            if duplicate_count > 0:
                issues.append({"check": "DUPLICATE_SIGNAL", "message": f"duplicate_count={duplicate_count}"})

        if context.regime_result is not None:
            if context.regime_result.regime == MarketRegimeType.CHOPPY:
                issues.append({"check": "REGIME_TRADE_ALLOWED", "message": "CHOPPY regime must not trade"})
            if not self._is_regime_strategy_compatible(context.regime_result.regime, contract.strategy_code):
                issues.append(
                    {
                        "check": "REGIME_STRATEGY_MATCH",
                        "message": f"strategy={contract.strategy_code} incompatible with regime={context.regime_result.regime.value}",
                    }
                )

        spread = context.market_snapshot.spread if context.market_snapshot else None
        if spread is not None and float(spread) > float(self.settings.max_spread):
            issues.append({"check": "SPREAD_LIMIT", "message": f"spread={spread} > max_spread={self.settings.max_spread}"})

        if symbol_id is not None:
            open_positions = self.position_repository.get_open_positions(symbol_id=symbol_id)
            if len(open_positions) >= int(self.settings.max_open_positions_per_symbol):
                issues.append(
                    {
                        "check": "OPEN_POSITION_LIMIT",
                        "message": f"open_positions={len(open_positions)} >= limit={self.settings.max_open_positions_per_symbol}",
                    }
                )

        validated_at = datetime.now(timezone.utc)
        if issues:
            self.signal_repository.create_signal_validation(
                signal_id=signal_id,
                validator_name="SignalValidator",
                status="REJECTED",
                validated_at=validated_at,
                rejection_reason="SIGNAL_VALIDATION_FAILED",
                details={"issues": issues},
            )
            self.signal_repository.session.commit()

            context.signal_validation = ValidationResult(
                status=ValidationStatus.REJECTED,
                reason="SIGNAL_VALIDATION_FAILED",
                validator_name="SignalValidator",
                details={"issues": issues},
            )
            context.reject("SIGNAL_VALIDATION_FAILED", {"issues": issues})
            return context

        self.signal_repository.create_signal_validation(
            signal_id=signal_id,
            validator_name="SignalValidator",
            status="PASSED",
            validated_at=validated_at,
            rejection_reason=None,
            details={"message": "Signal validation passed"},
        )
        self.signal_repository.session.commit()

        context.signal_validation = ValidationResult(
            status=ValidationStatus.PASSED,
            reason=None,
            validator_name="SignalValidator",
            details={"issues": []},
        )
        return context
