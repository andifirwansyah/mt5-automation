"""Service and strategy shell registry for strategy engine module."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

from .contracts import StrategyEngineRequest
from .errors import StrategyEngineInputError, StrategyNotRegisteredError
from .models import RawSignalCandidate


class BaseStrategy(ABC):
    """Base strategy interface for strategy engine shell."""

    key: str

    @abstractmethod
    def evaluate(self, request: StrategyEngineRequest) -> RawSignalCandidate:
        """Evaluate request and return raw signal candidate."""


@dataclass(slots=True)
class StrategyRegistry:
    """Simple in-memory strategy registry."""

    _strategies: dict[str, BaseStrategy]

    def register(self, strategy: BaseStrategy) -> None:
        self._strategies[strategy.key] = strategy

    def resolve(self, strategy_key: str) -> BaseStrategy:
        strategy = self._strategies.get(strategy_key)
        if strategy is None:
            raise StrategyNotRegisteredError(f"Strategy not registered: {strategy_key}")
        return strategy


class NoopWaitStrategy(BaseStrategy):
    """No-op strategy for smoke tests and WAIT decisions."""

    key = "noop_wait"

    def evaluate(self, request: StrategyEngineRequest) -> RawSignalCandidate:
        return RawSignalCandidate(
            symbol=request.market_frame.symbol,
            timeframe=request.market_frame.timeframe,
            strategy_key=self.key,
            direction="WAIT",
            confidence=0.30,
            reason="Noop strategy default output for shell/testing flow.",
            created_at=datetime.now(tz=UTC),
            metadata={"mode": "noop"},
        )


class TrendFollowPullbackStrategy(BaseStrategy):
    """Dummy trend-follow strategy for shell behavior tests."""

    key = "trend_follow_pullback"

    def evaluate(self, request: StrategyEngineRequest) -> RawSignalCandidate:
        frame = request.market_frame.frame
        close_prices = pd.to_numeric(frame["close"], errors="coerce")
        if len(close_prices.index) < 2 or close_prices.isna().any():
            return _wait_candidate(
                request=request,
                strategy_key=self.key,
                reason="Insufficient valid close data for trend follow evaluation.",
            )

        latest = float(close_prices.iloc[-1])
        previous = float(close_prices.iloc[-2])
        direction = "BUY" if latest > previous else "SELL" if latest < previous else "WAIT"
        confidence = 0.60 if direction != "WAIT" else 0.35

        return RawSignalCandidate(
            symbol=request.market_frame.symbol,
            timeframe=request.market_frame.timeframe,
            strategy_key=self.key,
            direction=direction,
            confidence=confidence,
            reason="Dummy trend-follow pullback strategy decision.",
            created_at=datetime.now(tz=UTC),
            metadata={"latest_close": latest, "previous_close": previous},
        )


class RangeMeanReversionStrategy(BaseStrategy):
    """Dummy range strategy for shell behavior tests."""

    key = "range_mean_reversion"

    def evaluate(self, request: StrategyEngineRequest) -> RawSignalCandidate:
        frame = request.market_frame.frame
        close_prices = pd.to_numeric(frame["close"], errors="coerce")
        high_prices = pd.to_numeric(frame["high"], errors="coerce")
        low_prices = pd.to_numeric(frame["low"], errors="coerce")
        if close_prices.isna().any() or high_prices.isna().any() or low_prices.isna().any():
            return _wait_candidate(
                request=request,
                strategy_key=self.key,
                reason="Invalid OHLC numeric values for range evaluation.",
            )

        latest_close = float(close_prices.iloc[-1])
        range_high = float(high_prices.max())
        range_low = float(low_prices.min())
        range_span = max(1e-9, range_high - range_low)
        position_ratio = (latest_close - range_low) / range_span

        if position_ratio <= 0.25:
            direction = "BUY"
        elif position_ratio >= 0.75:
            direction = "SELL"
        else:
            direction = "WAIT"

        confidence = 0.55 if direction != "WAIT" else 0.35
        return RawSignalCandidate(
            symbol=request.market_frame.symbol,
            timeframe=request.market_frame.timeframe,
            strategy_key=self.key,
            direction=direction,
            confidence=confidence,
            reason="Dummy range mean-reversion strategy decision.",
            created_at=datetime.now(tz=UTC),
            metadata={"position_ratio": round(position_ratio, 4)},
        )


def _wait_candidate(request: StrategyEngineRequest, strategy_key: str, reason: str) -> RawSignalCandidate:
    return RawSignalCandidate(
        symbol=request.market_frame.symbol,
        timeframe=request.market_frame.timeframe,
        strategy_key=strategy_key,
        direction="WAIT",
        confidence=0.30,
        reason=reason,
        created_at=datetime.now(tz=UTC),
        metadata={"mode": "guard_wait"},
    )


class StrategyEngineService:
    """Entry service for executing selected strategy through registry."""

    def __init__(self, registry: StrategyRegistry | None = None) -> None:
        self._registry = registry or self._build_default_registry()

    @property
    def registry(self) -> StrategyRegistry:
        """Expose strategy registry for testing/debug."""
        return self._registry

    def execute(self, request: StrategyEngineRequest) -> RawSignalCandidate:
        """Execute selected strategy or return noop WAIT for WAIT decision."""
        if request.selected_strategy is None or request.market_frame is None:
            raise StrategyEngineInputError("selected_strategy and market_frame must be provided.")

        selected = request.selected_strategy
        strategy_key = selected.strategy_key
        if selected.decision == "WAIT" or strategy_key == "WAIT":
            strategy_key = NoopWaitStrategy.key

        strategy = self._registry.resolve(strategy_key)
        return strategy.evaluate(request)

    def _build_default_registry(self) -> StrategyRegistry:
        registry = StrategyRegistry(_strategies={})
        registry.register(NoopWaitStrategy())
        registry.register(TrendFollowPullbackStrategy())
        registry.register(RangeMeanReversionStrategy())
        return registry
