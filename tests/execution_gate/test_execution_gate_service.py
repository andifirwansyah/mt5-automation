from datetime import UTC, datetime

from ai_trading_automation.modules.execution_gate import ExecutionGateRequest, ExecutionGateService
from ai_trading_automation.modules.pre_trade_simulation.models import SimulationResult
from ai_trading_automation.modules.risk_engine.models import RiskPlan
from ai_trading_automation.modules.signal_contract.models import SignalContract
from ai_trading_automation.modules.signal_validator.models import SignalValidationResult


def _signal() -> SignalContract:
    return SignalContract.model_validate(
        {
            "signal_id": "sig-gate-1",
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "direction": "BUY",
            "entry_price": 2350.0,
            "stop_loss": 2345.0,
            "take_profit": 2360.0,
            "strategy_key": "trend_follow_pullback",
            "confidence": 0.78,
            "reason": "gate test",
            "created_at": datetime.now(tz=UTC),
            "metadata": {},
        }
    )


def _risk_plan(risk_percent: float = 0.5, risk_reward_ratio: float = 2.0) -> RiskPlan:
    return RiskPlan(
        risk_amount=100.0,
        risk_percent=risk_percent,
        lot_size=20.0,
        stop_loss=2345.0,
        risk_reward_ratio=risk_reward_ratio,
        max_loss=100.0,
        notes=[],
    )


def _simulation(passed: bool = True) -> SimulationResult:
    return SimulationResult(
        passed=passed,
        scenario_results={"worst_case_exceeded": not passed},
        estimated_slippage=0.05,
        spread_risk=0.04,
        worst_case_loss=110.0,
        notes=[],
    )


def test_approve_path() -> None:
    service = ExecutionGateService()
    request = ExecutionGateRequest(
        signal_validation=SignalValidationResult(
            is_valid=True,
            score=82.0,
            errors=[],
            warnings=[],
            rejection_reason=None,
            validated_signal=_signal(),
        ),
        risk_plan=_risk_plan(risk_percent=0.5),
        simulation_result=_simulation(passed=True),
    )

    decision = service.decide(request)

    assert decision.decision == "APPROVE"


def test_reject_invalid_signal() -> None:
    service = ExecutionGateService()
    request = ExecutionGateRequest(
        signal_validation=SignalValidationResult(
            is_valid=False,
            score=20.0,
            errors=["invalid"],
            warnings=[],
            rejection_reason="Signal validation failed",
            validated_signal=None,
        ),
        risk_plan=_risk_plan(),
        simulation_result=_simulation(passed=True),
    )

    decision = service.decide(request)

    assert decision.decision == "REJECT"
    assert "invalid signal" in decision.reason.lower()


def test_reduce_risk_path() -> None:
    service = ExecutionGateService()
    request = ExecutionGateRequest(
        signal_validation=SignalValidationResult(
            is_valid=True,
            score=80.0,
            errors=[],
            warnings=[],
            rejection_reason=None,
            validated_signal=_signal(),
        ),
        risk_plan=_risk_plan(risk_percent=0.95, risk_reward_ratio=2.0),
        simulation_result=_simulation(passed=True),
    )

    decision = service.decide(request)

    assert decision.decision == "REDUCE_RISK"
