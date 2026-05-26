from datetime import datetime, timedelta

import pandas as pd
import pytest

from ai_trading_automation.modules.ohlcv_validation.models import ValidatedOHLCVFrame
from ai_trading_automation.modules.strategy_engine import (
    NoopWaitStrategy,
    StrategyEngineRequest,
    StrategyEngineService,
    StrategyNotRegisteredError,
)
from ai_trading_automation.modules.strategy_selector.models import SelectedStrategy


def _build_market_frame(close_values: list[float]) -> ValidatedOHLCVFrame:
    start = datetime(2026, 1, 1, 0, 0, 0)
    rows: list[dict[str, object]] = []
    for index, close_value in enumerate(close_values):
        open_value = close_values[index - 1] if index > 0 else close_value
        high_value = max(open_value, close_value) + 0.3
        low_value = min(open_value, close_value) - 0.3
        rows.append(
            {
                "timestamp": start + timedelta(hours=index),
                "open": float(open_value),
                "high": float(high_value),
                "low": float(low_value),
                "close": float(close_value),
                "volume": float(100 + index),
            }
        )

    return ValidatedOHLCVFrame(symbol="XAUUSD", timeframe="H1", frame=pd.DataFrame(rows))


def _selected_strategy(strategy_key: str, decision: str = "SELECT") -> SelectedStrategy:
    return SelectedStrategy(
        symbol="XAUUSD",
        timeframe="H1",
        regime="TREND_UP",
        strategy_key=strategy_key,
        decision=decision,
        confidence=0.7,
        reason="test",
        candidate_strategies=[strategy_key],
    )


def test_registry_resolve_known_strategy() -> None:
    service = StrategyEngineService()
    strategy = service.registry.resolve("trend_follow_pullback")

    assert strategy.key == "trend_follow_pullback"


def test_registry_resolve_unknown_strategy_raises() -> None:
    service = StrategyEngineService()

    with pytest.raises(StrategyNotRegisteredError):
        service.registry.resolve("unknown_strategy")


def test_noop_strategy_output_for_wait_decision() -> None:
    service = StrategyEngineService()
    request = StrategyEngineRequest(
        selected_strategy=_selected_strategy(strategy_key="WAIT", decision="WAIT"),
        market_frame=_build_market_frame([100.0, 100.1, 100.2]),
    )

    result = service.execute(request)

    assert result.strategy_key == NoopWaitStrategy.key
    assert result.direction == "WAIT"
    assert result.confidence <= 0.35


def test_unknown_selected_strategy_raises_error() -> None:
    service = StrategyEngineService()
    request = StrategyEngineRequest(
        selected_strategy=_selected_strategy(strategy_key="not_exists", decision="SELECT"),
        market_frame=_build_market_frame([100.0, 100.1, 100.2]),
    )

    with pytest.raises(StrategyNotRegisteredError):
        service.execute(request)


def test_trend_follow_shell_generates_direction() -> None:
    service = StrategyEngineService()
    request = StrategyEngineRequest(
        selected_strategy=_selected_strategy(strategy_key="trend_follow_pullback", decision="SELECT"),
        market_frame=_build_market_frame([100.0, 100.2, 100.4, 100.7]),
    )

    result = service.execute(request)

    assert result.direction in {"BUY", "SELL", "WAIT"}
    assert result.strategy_key == "trend_follow_pullback"
