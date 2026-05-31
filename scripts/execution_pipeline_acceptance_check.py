"""Acceptance checks for execution pipeline engines."""

from __future__ import annotations

import socket
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config.settings import get_settings
from src.domain.enums import ExecutionDecisionStatus, MarketRegimeType, OrderExecutionStatus, SignalDirection, ValidationStatus
from src.domain.models.broker_health import BrokerHealth
from src.domain.models.edge_result import EdgeResult
from src.domain.models.order_result import OrderResult
from src.domain.models.regime_result import RegimeResult
from src.domain.models.risk_plan import RiskPlan
from src.domain.models.signal import SignalContract
from src.domain.models.simulation_result import SimulationResult
from src.domain.models.validation_result import ValidationResult
from src.engines.execution_engine import ExecutionEngine
from src.engines.execution_gate import ExecutionGate
from src.infrastructure.database.models import ExecutionDecision as ExecutionDecisionModel
from src.infrastructure.database.models import Strategy
from src.infrastructure.database.session import SessionLocal
from src.pipeline.trading_context import TradingContext
from src.repositories.bot_repository import BotRepository
from src.repositories.execution_repository import ExecutionRepository
from src.repositories.market_repository import MarketRepository
from src.repositories.safety_repository import SafetyRepository
from src.repositories.signal_repository import SignalRepository
from src.services.bot_runtime_service import BotRuntimeService


class FakeOrderExecutor:
    """Track order_check/order_send flow without real MT5."""

    def __init__(self) -> None:
        self.order_check_called = 0
        self.send_called = 0

    def build_market_order_request(self, signal: SignalContract, risk_plan: RiskPlan) -> dict:
        return {
            "symbol": signal.symbol,
            "volume": risk_plan.lot_size,
            "price": signal.entry_price,
            "sl": risk_plan.stop_loss,
            "tp": risk_plan.take_profit,
        }

    def order_check(self, request: dict) -> dict:
        self.order_check_called += 1
        return {"retcode": 10009, "comment": "OK"}

    def send_market_order(self, signal: SignalContract, risk_plan: RiskPlan, decision) -> OrderResult:
        self.send_called += 1
        return OrderResult(
            status=OrderExecutionStatus.FILLED,
            dry_run=False,
            submitted_at=datetime.now(timezone.utc),
            order_ticket=123456,
            request_payload=self.build_market_order_request(signal, risk_plan),
            response_payload={"retcode": 10009, "comment": "FILLED"},
        )


def build_context(symbol_name: str, symbol_id: uuid.UUID, signal_id: uuid.UUID) -> TradingContext:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    context = TradingContext.from_candle_event(
        {
            "symbol": symbol_name,
            "timeframe": "M5",
            "candle_time": now.isoformat(),
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "tick_volume": 1,
        }
    )
    context.ingestion_result = {"symbol_id": symbol_id, "timeframe_ids": {"M5": uuid.uuid4()}}
    context.signal_contract = SignalContract(
        symbol=symbol_name,
        timeframe="M5",
        direction=SignalDirection.BUY,
        entry_price=2300.0,
        stop_loss=2298.0,
        take_profit=2304.0,
        lot_size=0.1,
        confidence=0.8,
        generated_at=now,
        strategy_code="EMA_ATR_TREND",
        metadata={"signal_id": str(signal_id), "entry_type": "MARKET", "side": "BUY"},
    )
    context.data_quality_result = ValidationResult(status=ValidationStatus.PASSED, validator_name="dq")
    context.market_event_result = ValidationResult(status=ValidationStatus.PASSED, validator_name="me")
    context.regime_result = RegimeResult(regime=MarketRegimeType.TRENDING_BULLISH, confidence=0.8, is_tradeable=True, features={})
    context.signal_validation = ValidationResult(status=ValidationStatus.PASSED, validator_name="sv")
    context.historical_edge = EdgeResult(passed=True, sample_size=50, win_rate=0.55, expectancy=10.0)
    context.risk_plan = RiskPlan(
        passed=True,
        lot_size=0.1,
        entry_price=2300.0,
        stop_loss=2298.0,
        take_profit=2304.0,
        risk_per_trade_pct=1.0,
        max_daily_loss_pct=5.0,
        details={"risk_amount": 100.0, "contract_size": 100.0, "rr_ratio": 2.0},
    )
    context.simulation_result = SimulationResult(passed=True, expected_profit=40.0, expected_drawdown=80.0, slippage_estimate=0.02)
    context.broker_health = BrokerHealth(is_healthy=True, is_connected=True, is_trade_allowed=True, spread=5.0)
    return context


def main() -> None:
    session = SessionLocal()
    try:
        bot_repo = BotRepository(session)
        runtime = BotRuntimeService(bot_repo)
        bot = runtime.register_bot_instance(
            instance_name="execution-ac-test",
            host_name=socket.gethostname(),
            process_id=99994,
            metadata={"scope": "execution_pipeline_acceptance"},
        )
        runtime.mark_running(bot.id)

        market_repo = MarketRepository(session)
        symbol = market_repo.get_or_create_symbol(name=f"XAUUSD_EXEC_AC_{int(datetime.now(timezone.utc).timestamp())}")
        strategy = session.execute(select(Strategy).where(Strategy.code == "EMA_ATR_TREND")).scalar_one_or_none()
        if strategy is None:
            strategy = Strategy(code="EMA_ATR_TREND", name="EMA ATR Trend", description="Trend", is_active=True, metadata_json={})
            session.add(strategy)
            session.flush()
        session.commit()

        signal_repo = SignalRepository(session)
        signal_row = signal_repo.create_signal(
            trace_id=bot.id,
            symbol_id=symbol.id,
            timeframe_id=market_repo.get_or_create_timeframe(code="M5", minutes=5).id,
            strategy_id=strategy.id,
            direction="BUY",
            status="GENERATED",
            signal_time=datetime.now(timezone.utc),
            entry_price=2300.0,
            stop_loss=2298.0,
            take_profit=2304.0,
            lot_size=0.1,
            confidence=0.8,
            features={},
            raw_payload={},
        )
        session.commit()

        execution_repo = ExecutionRepository(session)
        safety_repo = SafetyRepository(session)

        # CASE 1: DRY_RUN should not send order
        settings_dry = get_settings().model_copy(update={"auto_trade": True, "dry_run": True, "approval_required": False})
        gate_dry = ExecutionGate(execution_repository=execution_repo, safety_repository=safety_repo, settings=settings_dry)
        fake_executor_dry = FakeOrderExecutor()
        exec_dry = ExecutionEngine(execution_repository=execution_repo, safety_repository=safety_repo, order_executor=fake_executor_dry, settings=settings_dry)

        context_dry = build_context(symbol.name, symbol.id, signal_row.id)
        context_dry = gate_dry.run(context_dry)
        context_dry = exec_dry.run(context_dry)

        # CASE 2: APPROVE_AUTO + DRY_RUN=false should call order_send and order_check first
        settings_live = get_settings().model_copy(update={"auto_trade": True, "dry_run": False, "approval_required": False})
        gate_live = ExecutionGate(execution_repository=execution_repo, safety_repository=safety_repo, settings=settings_live)
        fake_executor_live = FakeOrderExecutor()
        exec_live = ExecutionEngine(execution_repository=execution_repo, safety_repository=safety_repo, order_executor=fake_executor_live, settings=settings_live)

        context_live = build_context(symbol.name, symbol.id, signal_row.id)
        context_live = gate_live.run(context_live)
        context_live = exec_live.run(context_live)

        decisions = session.execute(select(ExecutionDecisionModel).where(ExecutionDecisionModel.signal_id == signal_row.id)).scalars().all()
        decision_saved = len(decisions) >= 2

        dry_run_no_send = (
            context_dry.execution_decision is not None
            and context_dry.execution_decision.status == ExecutionDecisionStatus.DRY_RUN
            and fake_executor_dry.send_called == 0
        )

        approve_auto_sends = (
            context_live.execution_decision is not None
            and context_live.execution_decision.status == ExecutionDecisionStatus.APPROVE_AUTO
            and fake_executor_live.send_called >= 1
        )

        order_check_before_send = fake_executor_live.order_check_called >= fake_executor_live.send_called >= 1

        print("execution_decision_saved", decision_saved)
        print("dry_run_no_order_send", dry_run_no_send)
        print("approve_auto_can_send", approve_auto_sends)
        print("order_check_before_order_send", order_check_before_send)
    finally:
        session.close()


if __name__ == "__main__":
    main()
