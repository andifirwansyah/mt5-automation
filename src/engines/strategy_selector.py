"""Strategy selector engine based on market regime and active strategy configs."""

from __future__ import annotations

import uuid

from src.domain.enums import MarketRegimeType
from src.domain.models.strategy_selection import StrategySelectionResult
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories.strategy_repository import StrategyRepository


class StrategySelector(PipelineStep):
    """Select active strategy according to detected market regime."""

    @property
    def name(self) -> str:
        return "StrategySelector"

    def __init__(self, strategy_repository: StrategyRepository) -> None:
        self.strategy_repository = strategy_repository

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

    def _preferred_code_tokens(self, regime: MarketRegimeType) -> list[str]:
        if regime in (MarketRegimeType.TRENDING_BULLISH, MarketRegimeType.TRENDING_BEARISH):
            return ["EMA_ATR_TREND", "TREND"]
        if regime == MarketRegimeType.RANGING:
            return ["RANGE_REVERSION", "REVERSION", "MEAN_REVERSION"]
        if regime == MarketRegimeType.HIGH_VOLATILITY:
            return ["VOLATILITY_BREAKOUT", "BREAKOUT"]
        return []

    def run(self, context: TradingContext) -> TradingContext:
        if context.regime_result is None:
            context.reject("NO_REGIME_RESULT", {"message": "regime_result is required before strategy selection"})
            return context

        regime = context.regime_result.regime
        if regime == MarketRegimeType.CHOPPY:
            context.reject("NO_STRATEGY_SELECTED", {"message": "CHOPPY regime must be no trade"})
            return context

        symbol_id = self._as_uuid((context.ingestion_result or {}).get("symbol_id"))
        timeframe_id = self._as_uuid(((context.ingestion_result or {}).get("timeframe_ids") or {}).get(context.timeframe))
        if symbol_id is None or timeframe_id is None:
            context.reject("NO_STRATEGY_SELECTED", {"message": "symbol/timeframe references missing in ingestion result"})
            return context

        strategies = self.strategy_repository.get_active_strategies()
        if not strategies:
            context.reject("NO_STRATEGY_SELECTED", {"message": "No active strategies found"})
            return context

        preferred_tokens = self._preferred_code_tokens(regime)
        candidates = [s for s in strategies if any(token in s.code.upper() for token in preferred_tokens)]
        if not candidates:
            context.reject("NO_STRATEGY_SELECTED", {"message": f"No strategy matched regime={regime.value}"})
            return context

        selected = None
        selected_config = {}
        for strategy in candidates:
            configs = self.strategy_repository.get_active_strategy_configs(
                strategy_id=strategy.id,
                symbol_id=symbol_id,
                timeframe_id=timeframe_id,
            )
            config_payload = configs[0].config if configs else {}

            if regime == MarketRegimeType.HIGH_VOLATILITY and not bool(config_payload.get("allow_high_volatility", True)):
                continue

            selected = strategy
            selected_config = config_payload
            break

        if selected is None:
            context.reject("NO_STRATEGY_SELECTED", {"message": "No strategy passed config constraints"})
            return context

        self.strategy_repository.create_strategy_selection(
            trace_id=context.trace_id,
            symbol_id=symbol_id,
            timeframe_id=timeframe_id,
            strategy_id=selected.id,
            score=round(float(context.regime_result.confidence), 4),
            reason=f"Matched by regime={regime.value}",
            details={"regime": regime.value, "config": selected_config},
        )
        self.strategy_repository.session.commit()

        context.strategy_selection = StrategySelectionResult(
            strategy_code=selected.code,
            strategy_name=selected.name,
            score=float(context.regime_result.confidence),
            reason=f"Selected for regime={regime.value}",
            config=selected_config,
            details={"strategy_id": str(selected.id)},
        )
        return context
