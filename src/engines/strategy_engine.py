"""Strategy execution engine to generate raw signals from selected strategy."""

from __future__ import annotations

from collections.abc import Mapping

from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.strategies import EmaAtrTrendStrategy, RangeReversionStrategy, VolatilityBreakoutStrategy
from src.strategies.base_strategy import BaseStrategy


class StrategyEngine(PipelineStep):
    """Execute selected strategy and produce raw signal."""

    @property
    def name(self) -> str:
        return "StrategyEngine"

    def __init__(self, strategy_registry: Mapping[str, BaseStrategy] | None = None, reject_on_no_signal: bool = True) -> None:
        self.reject_on_no_signal = reject_on_no_signal
        self.strategy_registry: dict[str, BaseStrategy] = dict(strategy_registry or {
            "EMA_ATR_TREND": EmaAtrTrendStrategy(),
            "VOLATILITY_BREAKOUT": VolatilityBreakoutStrategy(),
            "RANGE_REVERSION": RangeReversionStrategy(),
        })

    def _resolve_strategy(self, strategy_code: str) -> BaseStrategy | None:
        if strategy_code in self.strategy_registry:
            return self.strategy_registry[strategy_code]
        for key, strategy in self.strategy_registry.items():
            if key in strategy_code or strategy_code in key:
                return strategy
        return None

    def run(self, context: TradingContext) -> TradingContext:
        if context.strategy_selection is None:
            context.reject("NO_STRATEGY_SELECTED", {"message": "strategy_selection missing"})
            return context
        if context.market_snapshot is None or context.regime_result is None:
            context.reject("NO_MARKET_OR_REGIME", {"message": "market_snapshot and regime_result are required"})
            return context

        strategy_code = context.strategy_selection.strategy_code.upper()
        strategy = self._resolve_strategy(strategy_code)
        if strategy is None:
            context.reject("NO_STRATEGY_IMPLEMENTATION", {"strategy_code": strategy_code})
            return context

        signal = strategy.generate_signal(
            market_snapshot=context.market_snapshot,
            regime=context.regime_result,
            config=context.strategy_selection.config,
        )

        if signal is None:
            if self.reject_on_no_signal:
                context.reject("NO_SIGNAL_GENERATED", {"strategy_code": strategy_code})
            return context

        context.raw_signal = signal
        return context
