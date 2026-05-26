from datetime import UTC, datetime

from ai_trading_automation.config import AppSettings
from ai_trading_automation.core.database import create_db_engine, create_session_factory
from ai_trading_automation.modules.execution_gate.models import ExecutionDecision
from ai_trading_automation.modules.paper_execution import (
    CreatePaperOrderRequest,
    PaperExecutionService,
    PaperOrderRepository,
)
from ai_trading_automation.modules.position_monitor.models import PositionState
from ai_trading_automation.modules.risk_engine.models import RiskPlan
from ai_trading_automation.modules.signal_contract.models import SignalContract


def _signal() -> SignalContract:
    return SignalContract.model_validate(
        {
            "signal_id": "sig-paper-db-1",
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "direction": "BUY",
            "entry_price": 2350.0,
            "stop_loss": 2345.0,
            "take_profit": 2360.0,
            "strategy_key": "trend_follow_pullback",
            "confidence": 0.75,
            "reason": "paper db test",
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


def _decision() -> ExecutionDecision:
    return ExecutionDecision(
        decision="APPROVE",
        reason="test",
        risk_plan=_risk_plan(),
        signal=_signal(),
        created_at=datetime.now(tz=UTC),
    )


def test_create_and_read_order_with_db_backend(tmp_path) -> None:
    db_path = tmp_path / "paper_orders.db"
    settings = AppSettings(
        app_env="test",
        app_name="ai-trading-automation",
        db_connection="sqlite",
        database_url=f"sqlite+pysqlite:///{db_path}",
        trade_journal_backend="file",
        paper_execution_backend="db",
        strict_db_runtime=False,
    )
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)

    repository = PaperOrderRepository(session_factory=session_factory)
    repository.create_tables()

    service = PaperExecutionService(storage_backend="db", repository=repository)
    created = service.create_order(CreatePaperOrderRequest(execution_decision=_decision()))

    loaded = service.get_order(created.order_id)
    assert loaded is not None
    assert loaded.order_id == created.order_id
    assert loaded.status == "OPEN"
    assert loaded.signal_id == "sig-paper-db-1"

    service.sync_position_state(
        order_id=created.order_id,
        position_state=PositionState(
            order_id=created.order_id,
            status="CLOSED",
            direction="BUY",
            entry_price=2350.0,
            current_price=2360.0,
            unrealized_pnl=0.0,
            realized_pnl=200.0,
            exit_reason="TAKE_PROFIT_HIT",
            hit_stop_loss=False,
            hit_take_profit=True,
            updated_at=datetime.now(tz=UTC),
        ),
    )

    reloaded = service.get_order(created.order_id)
    assert reloaded is not None
    assert reloaded.status == "CLOSED"
    assert reloaded.closed_at is not None
