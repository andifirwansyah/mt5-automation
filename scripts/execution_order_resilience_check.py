"""Checks execution order raw payload persistence and failure resilience."""

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
from src.domain.models.execution_decision import ExecutionDecision
from src.domain.models.order_result import OrderResult
from src.domain.models.regime_result import RegimeResult
from src.domain.models.risk_plan import RiskPlan
from src.domain.models.signal import SignalContract
from src.domain.models.simulation_result import SimulationResult
from src.domain.models.validation_result import ValidationResult
from src.engines.execution_engine import ExecutionEngine
from src.infrastructure.database.models import ExecutionOrder, Strategy
from src.infrastructure.database.session import SessionLocal
from src.pipeline.trading_context import TradingContext
from src.repositories.bot_repository import BotRepository
from src.repositories.execution_repository import ExecutionRepository
from src.repositories.market_repository import MarketRepository
from src.repositories.safety_repository import SafetyRepository
from src.repositories.signal_repository import SignalRepository
from src.services.bot_runtime_service import BotRuntimeService


class SuccessExecutor:
    def build_market_order_request(self, signal: SignalContract, risk_plan: RiskPlan) -> dict:
        return {"symbol": signal.symbol, "price": signal.entry_price, "sl": risk_plan.stop_loss, "tp": risk_plan.take_profit}

    def order_check(self, request: dict) -> dict:
        return {"retcode": 10009, "comment": "OK"}

    def send_market_order(self, signal: SignalContract, risk_plan: RiskPlan, decision: ExecutionDecision) -> OrderResult:
        return OrderResult(
            status=OrderExecutionStatus.FILLED,
            dry_run=False,
            submitted_at=datetime.now(timezone.utc),
            order_ticket=987654,
            request_payload=self.build_market_order_request(signal, risk_plan),
            response_payload={"retcode": 10009, "comment": "FILLED"},
        )


class FailingExecutor(SuccessExecutor):
    def send_market_order(self, signal: SignalContract, risk_plan: RiskPlan, decision: ExecutionDecision) -> OrderResult:
        raise RuntimeError("broker timeout")


def build_context(symbol_name: str, symbol_id: uuid.UUID, signal_id: uuid.UUID) -> TradingContext:
    now = datetime.now(timezone.utc)
    ctx = TradingContext.from_candle_event(
        {
            "symbol": symbol_name,
            "timeframe": "M5",
            "candle_time": now.isoformat(),
            "open": 1,
            "high": 2,
            "low": 0.5,
            "close": 1.5,
            "tick_volume": 1,
        }
    )
    ctx.ingestion_result = {"symbol_id": symbol_id, "timeframe_ids": {"M5": uuid.uuid4()}, "account_info": {}}
    ctx.signal_contract = SignalContract(
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
        metadata={"signal_id": str(signal_id), "side": "BUY", "entry_type": "MARKET"},
    )
    ctx.data_quality_result = ValidationResult(status=ValidationStatus.PASSED)
    ctx.market_event_result = ValidationResult(status=ValidationStatus.PASSED)
    ctx.regime_result = RegimeResult(regime=MarketRegimeType.TRENDING_BULLISH, confidence=0.8, is_tradeable=True, features={})
    ctx.signal_validation = ValidationResult(status=ValidationStatus.PASSED)
    ctx.historical_edge = EdgeResult(passed=True, sample_size=40, win_rate=0.55, expectancy=10)
    ctx.risk_plan = RiskPlan(
        passed=True,
        lot_size=0.1,
        entry_price=2300.0,
        stop_loss=2298.0,
        take_profit=2304.0,
        risk_per_trade_pct=1.0,
        max_daily_loss_pct=5.0,
        details={"risk_amount": 100.0, "contract_size": 100.0, "rr_ratio": 2.0},
    )
    ctx.simulation_result = SimulationResult(passed=True, expected_profit=40.0, expected_drawdown=80.0, slippage_estimate=0.01)
    ctx.broker_health = BrokerHealth(is_healthy=True, is_connected=True, is_trade_allowed=True, spread=2.0)
    ctx.execution_decision = ExecutionDecision(status=ExecutionDecisionStatus.APPROVE_AUTO, details={})
    return ctx


def main() -> None:
    session = SessionLocal()
    try:
        bot_repo = BotRepository(session)
        runtime = BotRuntimeService(bot_repo)
        bot = runtime.register_bot_instance("exec-resilience", socket.gethostname(), 99993, {"scope": "execution_resilience"})
        runtime.mark_running(bot.id)

        market_repo = MarketRepository(session)
        symbol = market_repo.get_or_create_symbol(name=f"XAUUSD_EXEC_RES_{int(datetime.now(timezone.utc).timestamp())}")
        strategy = session.execute(select(Strategy).where(Strategy.code == "EMA_ATR_TREND")).scalar_one_or_none()
        if strategy is None:
            strategy = Strategy(code="EMA_ATR_TREND", name="EMA ATR Trend", description="Trend", is_active=True, metadata_json={})
            session.add(strategy)
            session.flush()
        tf = market_repo.get_or_create_timeframe(code="M5", minutes=5)
        signal_repo = SignalRepository(session)
        signal = signal_repo.create_signal(
            trace_id=bot.id,
            symbol_id=symbol.id,
            timeframe_id=tf.id,
            strategy_id=strategy.id,
            direction="BUY",
            status="GENERATED",
            signal_time=datetime.now(timezone.utc),
            entry_price=2300,
            stop_loss=2298,
            take_profit=2304,
            lot_size=0.1,
            confidence=0.8,
            features={},
            raw_payload={},
        )
        session.commit()

        execution_repo = ExecutionRepository(session)
        safety_repo = SafetyRepository(session)
        settings_live = get_settings().model_copy(update={"dry_run": False, "auto_trade": True, "approval_required": False})

        # success case -> raw request & response saved
        success_engine = ExecutionEngine(execution_repo, safety_repo, SuccessExecutor(), settings_live)
        ctx_ok = build_context(symbol.name, symbol.id, signal.id)
        ctx_ok = success_engine.run(ctx_ok)

        order_row = session.execute(
            select(ExecutionOrder).where(ExecutionOrder.signal_id == signal.id).order_by(ExecutionOrder.created_at.desc()).limit(1)
        ).scalar_one_or_none()

        raw_request_response_saved = bool(
            order_row
            and isinstance(order_row.broker_response, dict)
            and "request" in order_row.broker_response
            and "response" in order_row.broker_response
        )

        # failing case -> no crash (handled, context rejected)
        failing_engine = ExecutionEngine(execution_repo, safety_repo, FailingExecutor(), settings_live)
        ctx_fail = build_context(symbol.name, symbol.id, signal.id)
        try:
            ctx_fail = failing_engine.run(ctx_fail)
            no_crash_on_fail = ctx_fail.rejected and ctx_fail.rejection_reason == "ORDER_EXECUTION_FAILED"
        except Exception:
            no_crash_on_fail = False

        print("execution_order_raw_request_response_saved", raw_request_response_saved)
        print("order_failure_no_bot_crash", no_crash_on_fail)
    finally:
        session.close()


if __name__ == "__main__":
    main()
