from datetime import UTC, datetime

import pytest

from ai_trading_automation.modules.execution_gate.models import ExecutionDecision
from ai_trading_automation.modules.paper_execution import (
    CreatePaperOrderRequest,
    PaperExecutionBlockedError,
    PaperExecutionService,
)
from ai_trading_automation.modules.risk_engine.models import RiskPlan
from ai_trading_automation.modules.signal_contract.models import SignalContract


def _signal() -> SignalContract:
    return SignalContract.model_validate(
        {
            "signal_id": "sig-paper-1",
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "direction": "BUY",
            "entry_price": 2350.0,
            "stop_loss": 2345.0,
            "take_profit": 2360.0,
            "strategy_key": "trend_follow_pullback",
            "confidence": 0.75,
            "reason": "paper test",
            "created_at": datetime.now(tz=UTC),
            "metadata": {},
        }
    )


def _risk_plan() -> RiskPlan:
    return RiskPlan(
        risk_amount=100.0,
        risk_percent=1.0,
        lot_size=20.0,
        stop_loss=2345.0,
        risk_reward_ratio=2.0,
        max_loss=100.0,
        notes=[],
    )


def _decision(decision: str) -> ExecutionDecision:
    return ExecutionDecision(
        decision=decision,
        reason="test",
        risk_plan=_risk_plan(),
        signal=_signal(),
        created_at=datetime.now(tz=UTC),
    )


def test_approve_creates_paper_order() -> None:
    service = PaperExecutionService()

    order = service.create_order(CreatePaperOrderRequest(execution_decision=_decision("APPROVE")))

    assert order.order_id
    assert order.status == "OPEN"
    assert order.signal_id == "sig-paper-1"
    assert service.get_order(order.order_id) is not None


def test_reject_is_blocked() -> None:
    service = PaperExecutionService()

    with pytest.raises(PaperExecutionBlockedError):
        service.create_order(CreatePaperOrderRequest(execution_decision=_decision("REJECT")))
