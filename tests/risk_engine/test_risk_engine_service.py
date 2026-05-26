from datetime import UTC, datetime

import pytest

from ai_trading_automation.modules.risk_engine import (
    AccountRiskConfig,
    RiskEngineRequest,
    RiskEngineService,
    RiskEngineInputError,
    RiskLimitExceededError,
)
from ai_trading_automation.modules.signal_contract.models import SignalContract


def _signal(direction: str, entry: float, stop_loss: float, take_profit: float) -> SignalContract:
    return SignalContract.model_validate(
        {
            "signal_id": "sig-risk",
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "direction": direction,
            "entry_price": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "strategy_key": "trend_follow_pullback",
            "confidence": 0.7,
            "reason": "risk test",
            "created_at": datetime.now(tz=UTC),
            "metadata": {},
        }
    )


def test_calculate_normal_risk_plan() -> None:
    service = RiskEngineService()
    request = RiskEngineRequest(
        signal=_signal("BUY", entry=2350.0, stop_loss=2345.0, take_profit=2360.0),
        account_balance=10_000.0,
        daily_realized_loss=50.0,
        open_positions_count=1,
        requested_risk_percent=1.0,
        config=AccountRiskConfig(max_risk_per_trade_percent=1.0, max_daily_loss_percent=3.0, max_open_positions=3),
    )

    risk_plan = service.calculate(request)

    assert risk_plan.risk_amount == 100.0
    assert risk_plan.lot_size == 20.0
    assert risk_plan.risk_percent == 1.0
    assert risk_plan.max_loss == 100.0


def test_zero_stop_loss_distance_rejected() -> None:
    service = RiskEngineService()
    request = RiskEngineRequest(
        signal=_signal("BUY", entry=2350.0, stop_loss=2350.0, take_profit=2360.0),
        account_balance=10_000.0,
        daily_realized_loss=0.0,
        open_positions_count=0,
        requested_risk_percent=0.5,
    )

    with pytest.raises(RiskEngineInputError, match="stop_loss must be below entry_price"):
        service.calculate(request)


def test_max_risk_per_trade_exceeded_rejected() -> None:
    service = RiskEngineService()
    request = RiskEngineRequest(
        signal=_signal("SELL", entry=2350.0, stop_loss=2355.0, take_profit=2340.0),
        account_balance=10_000.0,
        daily_realized_loss=0.0,
        open_positions_count=0,
        requested_risk_percent=1.5,
        config=AccountRiskConfig(max_risk_per_trade_percent=1.0, max_daily_loss_percent=3.0, max_open_positions=3),
    )

    with pytest.raises(RiskLimitExceededError, match="exceeds max risk per trade"):
        service.calculate(request)
