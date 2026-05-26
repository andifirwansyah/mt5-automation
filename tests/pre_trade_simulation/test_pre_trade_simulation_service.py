from datetime import UTC, datetime

from ai_trading_automation.modules.pre_trade_simulation import (
    PreTradeSimulationRequest,
    PreTradeSimulationService,
    SimulationAssumptions,
)
from ai_trading_automation.modules.risk_engine.models import RiskPlan
from ai_trading_automation.modules.signal_contract.models import SignalContract
from ai_trading_automation.modules.signal_validator.models import SignalValidationResult


def _validated_signal() -> SignalContract:
    return SignalContract.model_validate(
        {
            "signal_id": "sig-sim-1",
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "direction": "BUY",
            "entry_price": 2350.0,
            "stop_loss": 2345.0,
            "take_profit": 2360.0,
            "strategy_key": "trend_follow_pullback",
            "confidence": 0.72,
            "reason": "simulation test",
            "created_at": datetime.now(tz=UTC),
            "metadata": {},
        }
    )


def _signal_validation_result() -> SignalValidationResult:
    signal = _validated_signal()
    return SignalValidationResult(
        is_valid=True,
        score=78.0,
        errors=[],
        warnings=[],
        rejection_reason=None,
        validated_signal=signal,
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


def test_normal_simulation_passes() -> None:
    service = PreTradeSimulationService()
    request = PreTradeSimulationRequest(
        signal_validation=_signal_validation_result(),
        risk_plan=_risk_plan(),
        assumptions=SimulationAssumptions(
            spread_percent=0.0004,
            slippage_percent=0.0004,
            adverse_move_factor=0.15,
            max_worst_case_loss_factor=1.35,
        ),
    )

    result = service.run(request)

    assert result.passed is True
    assert result.scenario_results["spread_extreme"] is False
    assert result.scenario_results["slippage_extreme"] is False
    assert result.scenario_results["worst_case_exceeded"] is False


def test_high_slippage_fails_simulation() -> None:
    service = PreTradeSimulationService()
    request = PreTradeSimulationRequest(
        signal_validation=_signal_validation_result(),
        risk_plan=_risk_plan(),
        assumptions=SimulationAssumptions(
            spread_percent=0.0004,
            slippage_percent=0.0040,
            adverse_move_factor=0.15,
            max_worst_case_loss_factor=1.50,
            slippage_extreme_threshold=0.0030,
        ),
    )

    result = service.run(request)

    assert result.passed is False
    assert result.scenario_results["slippage_extreme"] is True


def test_spread_extreme_fails_simulation() -> None:
    service = PreTradeSimulationService()
    request = PreTradeSimulationRequest(
        signal_validation=_signal_validation_result(),
        risk_plan=_risk_plan(),
        assumptions=SimulationAssumptions(
            spread_percent=0.0030,
            slippage_percent=0.0004,
            adverse_move_factor=0.15,
            max_worst_case_loss_factor=1.50,
            spread_extreme_threshold=0.0025,
        ),
    )

    result = service.run(request)

    assert result.passed is False
    assert result.scenario_results["spread_extreme"] is True
