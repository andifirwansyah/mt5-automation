from datetime import UTC, datetime

from ai_trading_automation.config import AppSettings
from ai_trading_automation.core.database import create_db_engine, create_session_factory
from ai_trading_automation.modules.execution_gate.models import ExecutionDecision
from ai_trading_automation.modules.pre_trade_simulation.models import SimulationResult
from ai_trading_automation.modules.risk_engine.models import RiskPlan
from ai_trading_automation.modules.signal_contract.models import SignalContract
from ai_trading_automation.modules.signal_validator.models import SignalValidationResult
from ai_trading_automation.modules.trade_journal import (
    JournalWriteRequest,
    TradeJournalRepository,
    TradeJournalService,
)


def _signal() -> SignalContract:
    return SignalContract.model_validate(
        {
            "signal_id": "sig-journal-db-1",
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "direction": "BUY",
            "entry_price": 2350.0,
            "stop_loss": 2345.0,
            "take_profit": 2360.0,
            "strategy_key": "trend_follow_pullback",
            "confidence": 0.76,
            "reason": "journal db test",
            "created_at": datetime.now(tz=UTC),
            "metadata": {},
        }
    )


def _signal_validation() -> SignalValidationResult:
    return SignalValidationResult(
        is_valid=True,
        score=80.0,
        errors=[],
        warnings=[],
        rejection_reason=None,
        validated_signal=_signal(),
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


def _simulation_result() -> SimulationResult:
    return SimulationResult(
        passed=True,
        scenario_results={"spread_extreme": False},
        estimated_slippage=0.05,
        spread_risk=0.04,
        worst_case_loss=110.0,
        notes=[],
    )


def _decision() -> ExecutionDecision:
    return ExecutionDecision(
        decision="APPROVE",
        reason="decision test",
        risk_plan=_risk_plan(),
        signal=_signal(),
        created_at=datetime.now(tz=UTC),
    )


def test_write_and_read_with_db_backend(tmp_path) -> None:
    db_path = tmp_path / "journal.db"
    settings = AppSettings(
        app_env="test",
        app_name="ai-trading-automation",
        db_connection="sqlite",
        database_url=f"sqlite+pysqlite:///{db_path}",
        trade_journal_backend="db",
        paper_execution_backend="memory",
        strict_db_runtime=False,
    )

    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)

    repository = TradeJournalRepository(session_factory=session_factory)
    repository.create_tables()

    service = TradeJournalService(storage_backend="db", repository=repository)
    entry = service.write_entry(
        JournalWriteRequest(
            signal_validation=_signal_validation(),
            risk_plan=_risk_plan(),
            simulation_result=_simulation_result(),
            execution_decision=_decision(),
            notes=["db backend"],
        )
    )

    loaded = service.read_entries()
    assert len(loaded) == 1
    assert loaded[0].journal_id == entry.journal_id
    assert loaded[0].execution_decision["decision"] == "APPROVE"
    assert loaded[0].notes == ["db backend"]
