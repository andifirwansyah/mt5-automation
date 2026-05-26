from datetime import UTC, datetime

from ai_trading_automation.modules.market_regime.models import MarketRegimeResult
from ai_trading_automation.modules.signal_contract.models import SignalContract
from ai_trading_automation.modules.signal_validator import (
    SignalValidationRequest,
    SignalValidatorService,
)


def _signal(direction: str, entry: float, stop_loss: float, take_profit: float) -> SignalContract:
    return SignalContract.model_validate(
        {
            "signal_id": "sig-test",
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "direction": direction,
            "entry_price": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "strategy_key": "trend_follow_pullback",
            "confidence": 0.75,
            "reason": "test signal",
            "created_at": datetime.now(tz=UTC),
            "metadata": {},
        }
    )


def _regime(regime: str) -> MarketRegimeResult:
    return MarketRegimeResult(
        symbol="XAUUSD",
        timeframe="H1",
        regime=regime,
        confidence=0.7,
        volatility_state="NORMAL_VOLATILITY",
        trend_strength=0.02,
        range_state="WIDE_RANGE",
        notes=[],
    )


def test_buy_stop_loss_above_entry_invalid() -> None:
    validator = SignalValidatorService()
    request = SignalValidationRequest(
        signal=_signal(direction="BUY", entry=2350.0, stop_loss=2351.0, take_profit=2360.0),
        market_regime=_regime("TREND_UP"),
    )

    result = validator.validate(request)

    assert result.is_valid is False
    assert any("BUY signal invalid: stop_loss must be below entry_price" in error for error in result.errors)


def test_sell_stop_loss_below_entry_invalid() -> None:
    validator = SignalValidatorService()
    request = SignalValidationRequest(
        signal=_signal(direction="SELL", entry=2350.0, stop_loss=2349.0, take_profit=2340.0),
        market_regime=_regime("TREND_DOWN"),
    )

    result = validator.validate(request)

    assert result.is_valid is False
    assert any("SELL signal invalid: stop_loss must be above entry_price" in error for error in result.errors)


def test_conflict_regime_rejected() -> None:
    validator = SignalValidatorService()
    request = SignalValidationRequest(
        signal=_signal(direction="SELL", entry=2350.0, stop_loss=2360.0, take_profit=2340.0),
        market_regime=_regime("TREND_UP"),
    )

    result = validator.validate(request)

    assert result.is_valid is False
    assert any("conflicts with TREND_UP" in error for error in result.errors)


def test_valid_signal_passes() -> None:
    validator = SignalValidatorService()
    request = SignalValidationRequest(
        signal=_signal(direction="BUY", entry=2350.0, stop_loss=2344.0, take_profit=2362.0),
        market_regime=_regime("TREND_UP"),
    )

    result = validator.validate(request)

    assert result.is_valid is True
    assert result.validated_signal is not None
    assert result.score >= 60.0
