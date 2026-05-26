from datetime import UTC, datetime

from ai_trading_automation.modules.execution_gate.models import ExecutionDecision
from ai_trading_automation.modules.pre_trade_simulation.models import SimulationResult
from ai_trading_automation.modules.risk_engine.models import RiskPlan
from ai_trading_automation.modules.signal_contract.models import SignalContract
from ai_trading_automation.modules.signal_validator.models import SignalValidationResult
from ai_trading_automation.modules.trade_journal import (
    JournalReadRequest,
    JournalWriteRequest,
    TradeJournalService,
)


def _signal() -> SignalContract:
    return SignalContract.model_validate(
        {
            "signal_id": "sig-journal-1",
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "direction": "BUY",
            "entry_price": 2350.0,
            "stop_loss": 2345.0,
            "take_profit": 2360.0,
            "strategy_key": "trend_follow_pullback",
            "confidence": 0.76,
            "reason": "journal test",
            "created_at": datetime.now(tz=UTC),
            "metadata": {},
        }
    )


def _signal_validation(is_valid: bool = True) -> SignalValidationResult:
    return SignalValidationResult(
        is_valid=is_valid,
        score=80.0 if is_valid else 20.0,
        errors=[] if is_valid else ["invalid"],
        warnings=[],
        rejection_reason=None if is_valid else "invalid signal",
        validated_signal=_signal() if is_valid else None,
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


def _simulation_result(passed: bool = True) -> SimulationResult:
    return SimulationResult(
        passed=passed,
        scenario_results={"spread_extreme": False},
        estimated_slippage=0.05,
        spread_risk=0.04,
        worst_case_loss=110.0,
        notes=[],
    )


def _decision(decision: str, include_signal: bool = True) -> ExecutionDecision:
    return ExecutionDecision(
        decision=decision,
        reason="decision test",
        risk_plan=_risk_plan(),
        signal=_signal() if include_signal else None,
        created_at=datetime.now(tz=UTC),
    )


def test_write_and_read_journal_entry(tmp_path) -> None:
    journal_path = tmp_path / "outputs" / "journals" / "trade_journal.jsonl"
    service = TradeJournalService(journal_path=journal_path)

    entry = service.write_entry(
        JournalWriteRequest(
            signal_validation=_signal_validation(is_valid=True),
            risk_plan=_risk_plan(),
            simulation_result=_simulation_result(passed=True),
            execution_decision=_decision("APPROVE"),
            notes=["approve path"],
        )
    )

    assert entry.journal_id
    assert entry.execution_decision["decision"] == "APPROVE"
    assert "reason" in entry.execution_decision

    loaded = service.read_entries(JournalReadRequest(journal_path=journal_path))
    assert len(loaded) == 1
    assert loaded[0].journal_id == entry.journal_id
    assert loaded[0].notes == ["approve path"]


def test_rejected_decision_is_journaled(tmp_path) -> None:
    journal_path = tmp_path / "outputs" / "journals" / "trade_journal.jsonl"
    service = TradeJournalService(journal_path=journal_path)

    service.write_entry(
        JournalWriteRequest(
            signal_validation=_signal_validation(is_valid=False),
            risk_plan=_risk_plan(),
            simulation_result=_simulation_result(passed=False),
            execution_decision=_decision("REJECT", include_signal=False),
            notes=["rejected trade"],
        )
    )

    loaded = service.read_entries(JournalReadRequest(journal_path=journal_path))
    assert len(loaded) == 1
    assert loaded[0].execution_decision["decision"] == "REJECT"
    assert loaded[0].signal is None
    assert loaded[0].notes == ["rejected trade"]
