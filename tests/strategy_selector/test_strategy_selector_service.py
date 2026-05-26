import pytest

from ai_trading_automation.modules.market_regime.models import MarketRegimeResult
from ai_trading_automation.modules.strategy_selector import (
    StrategySelectorRequest,
    StrategySelectorService,
)


def _regime_result(regime: str, confidence: float = 0.7) -> MarketRegimeResult:
    return MarketRegimeResult(
        symbol="XAUUSD",
        timeframe="H1",
        regime=regime,
        confidence=confidence,
        volatility_state="NORMAL_VOLATILITY",
        trend_strength=0.02,
        range_state="WIDE_RANGE",
        notes=[],
    )


def test_trend_regime_selects_trend_strategy() -> None:
    service = StrategySelectorService()

    selected = service.select(StrategySelectorRequest(market_regime=_regime_result("TREND_UP")))

    assert selected.decision == "SELECT"
    assert selected.strategy_key == "trend_follow_pullback"
    assert "trend up" in selected.reason.lower()


def test_choppy_regime_returns_wait() -> None:
    service = StrategySelectorService()

    selected = service.select(StrategySelectorRequest(market_regime=_regime_result("CHOPPY")))

    assert selected.decision == "WAIT"
    assert selected.strategy_key == "WAIT"


@pytest.mark.parametrize("regime", ["UNKNOWN", "NOT_REGISTERED"])
def test_unknown_regime_returns_wait(regime: str) -> None:
    service = StrategySelectorService()

    selected = service.select(StrategySelectorRequest(market_regime=_regime_result(regime)))

    assert selected.decision == "WAIT"
    assert selected.strategy_key == "WAIT"


def test_low_confidence_forces_wait() -> None:
    service = StrategySelectorService()
    request = StrategySelectorRequest(
        market_regime=_regime_result("TREND_UP", confidence=0.30),
        min_regime_confidence=0.45,
    )

    selected = service.select(request)

    assert selected.decision == "WAIT"
    assert selected.strategy_key == "WAIT"
    assert "threshold minimum" in selected.reason.lower()
