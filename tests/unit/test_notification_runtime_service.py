from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.config.settings import AppSettings
from src.domain.enums import ExecutionDecisionStatus, OrderExecutionStatus, SignalDirection
from src.domain.models.execution_decision import ExecutionDecision
from src.domain.models.order_result import OrderResult
from src.domain.models.risk_plan import RiskPlan
from src.domain.models.signal import SignalContract
from src.pipeline.trading_context import TradingContext
from src.services.notification_runtime_service import NotificationRuntimeService


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


class FakeDispatchService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, str | None]] = []

    def dispatch_event(self, *, event_type, payload, source_key=None):
        self.calls.append((event_type.value, payload, source_key))
        return []


def _build_context() -> TradingContext:
    now = datetime.now(timezone.utc)
    context = TradingContext.from_candle_event({"symbol": "XAUUSD", "timeframe": "M5", "candle_time": now.isoformat()})
    context.signal_contract = SignalContract(
        symbol="XAUUSD",
        timeframe="M5",
        direction=SignalDirection.BUY,
        entry_price=2345.1,
        stop_loss=2339.5,
        take_profit=2354.8,
        lot_size=0.1,
        confidence=0.8,
        generated_at=now,
        strategy_code="EMA_ATR_TREND",
        metadata={"signal_id": str(uuid.uuid4()), "reason": "trend continuation"},
    )
    context.execution_decision = ExecutionDecision(status=ExecutionDecisionStatus.DRY_RUN, details={})
    context.risk_plan = RiskPlan(
        passed=True,
        lot_size=0.1,
        entry_price=2345.1,
        stop_loss=2339.5,
        take_profit=2354.8,
        risk_per_trade_pct=1.0,
        max_daily_loss_pct=3.0,
        details={},
    )
    context.order_result = OrderResult(
        status=OrderExecutionStatus.DRY_RUN,
        dry_run=True,
        submitted_at=now,
        response_payload={"execution_order_id": str(uuid.uuid4())},
    )
    return context


def test_notification_runtime_service_processes_signal_and_trade_opened(monkeypatch) -> None:
    session = FakeSession()
    dispatch = FakeDispatchService()
    service = NotificationRuntimeService(session_factory=lambda: session, settings=AppSettings())
    monkeypatch.setattr(service, "_build_dispatch_service", lambda _: dispatch)

    service.process_trading_context(_build_context())

    assert [item[0] for item in dispatch.calls] == ["SIGNAL_READY", "TRADE_OPENED"]
    assert session.commits == 1
    assert session.closed is True


def test_notification_runtime_service_processes_closed_positions(monkeypatch) -> None:
    session = FakeSession()
    dispatch = FakeDispatchService()
    service = NotificationRuntimeService(session_factory=lambda: session, settings=AppSettings())
    monkeypatch.setattr(service, "_build_dispatch_service", lambda _: dispatch)

    now = datetime.now(timezone.utc)
    closed_position = type(
        "ClosedPosition",
        (),
        {
            "id": uuid.uuid4(),
            "side": "BUY",
            "entry_price": 2300.0,
            "close_price": 2310.0,
            "profit": 15.0,
            "opened_at": now,
            "closed_at": now,
            "details": {"symbol": "XAUUSD"},
        },
    )()

    service.process_closed_positions([closed_position])

    assert [item[0] for item in dispatch.calls] == ["TRADE_CLOSED"]
    assert session.commits == 1
