"""Acceptance smoke checks for TradingOrchestrator behavior."""

from __future__ import annotations

import socket
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.infrastructure.database.models import EngineRun
from src.infrastructure.database.session import SessionLocal
from src.orchestrators.trading_orchestrator import TradingOrchestrator
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.pipeline.trading_pipeline import PIPELINE_STEP_ORDER
from src.repositories.bot_repository import BotRepository
from src.services.bot_runtime_service import BotRuntimeService
from src.services.engine_audit_service import EngineAuditService


@dataclass
class DummyAuditRunner:
    """Simple runner to track executed steps in-memory."""

    executed: list[str]

    def run_and_audit(self, step: PipelineStep, context: TradingContext) -> TradingContext:
        self.executed.append(step.name)
        return step.run(context)


class PassStep(PipelineStep):
    def __init__(self, step_name: str) -> None:
        self._name = step_name

    @property
    def name(self) -> str:
        return self._name

    def run(self, context: TradingContext) -> TradingContext:
        return context


class RejectStep(PipelineStep):
    @property
    def name(self) -> str:
        return "REJECT_STEP"

    def run(self, context: TradingContext) -> TradingContext:
        context.reject(reason="REJECTED_BY_TEST", details={"source": "reject-step"})
        return context


class ExplodeStep(PipelineStep):
    @property
    def name(self) -> str:
        return "EXPLODE_STEP"

    def run(self, context: TradingContext) -> TradingContext:
        raise RuntimeError("intentional step failure")


def run_dummy_list_check() -> bool:
    audit = DummyAuditRunner(executed=[])
    steps: list[PipelineStep] = [PassStep("S1"), PassStep("S2"), PassStep("S3")]
    orchestrator = TradingOrchestrator(steps=steps, engine_audit_service=audit)
    context = orchestrator.run_cycle({"symbol": "XAUUSD", "timeframe": "M5", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "tick_volume": 10})
    return (audit.executed == ["S1", "S2", "S3"]) and (not context.rejected)


def run_reject_stop_check() -> bool:
    audit = DummyAuditRunner(executed=[])
    steps: list[PipelineStep] = [PassStep("S1"), RejectStep(), PassStep("S3")]
    orchestrator = TradingOrchestrator(steps=steps, engine_audit_service=audit)
    context = orchestrator.run_cycle({"symbol": "XAUUSD", "timeframe": "M5", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "tick_volume": 10})
    return context.rejected and context.rejection_reason == "REJECTED_BY_TEST" and audit.executed == ["S1", "REJECT_STEP"]


def run_exception_and_audit_failed_check() -> bool:
    session = SessionLocal()
    try:
        bot_repo = BotRepository(session)
        runtime = BotRuntimeService(bot_repo)
        bot = runtime.register_bot_instance(
            instance_name="orchestrator-ac-test",
            host_name=socket.gethostname(),
            process_id=99998,
            metadata={"scope": "orchestrator_acceptance"},
        )
        runtime.mark_running(bot.id)

        audit_service = EngineAuditService(bot_repository=bot_repo, bot_instance_id=bot.id)
        orchestrator = TradingOrchestrator(steps=[PassStep("S1"), ExplodeStep(), PassStep("S3")], engine_audit_service=audit_service)

        context = orchestrator.run_cycle({"symbol": "XAUUSD", "timeframe": "M5", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "tick_volume": 10})
        failed_rows = session.execute(
            select(EngineRun).where(EngineRun.trace_id == context.trace_id, EngineRun.engine_name == "EXPLODE_STEP", EngineRun.status == "FAILED")
        ).scalars().all()

        return context.rejected and context.rejection_reason == "PIPELINE_FATAL_ERROR" and len(failed_rows) >= 1
    finally:
        session.close()


def run_pipeline_order_check() -> bool:
    expected = (
        "KillSwitchMonitor",
        "DataCollectorEngine",
        "MarketDataIngestionEngine",
        "DataQualityGuard",
        "MarketEventFilter",
        "MarketRegimeEngine",
        "StrategySelector",
        "StrategyEngine",
        "SignalContractBuilder",
        "SignalValidator",
        "HistoricalEdgeValidator",
        "RiskEngine",
        "PreTradeSimulation",
        "BrokerHealthCheck",
        "ExecutionGate",
        "ApprovalEngine",
        "ExecutionEngine",
        "TradeJournalEngine",
        "RuntimeStateUpdater",
    )
    return PIPELINE_STEP_ORDER == expected


def main() -> None:
    print("dummy_steps_run", run_dummy_list_check())
    print("reject_stops_pipeline", run_reject_stop_check())
    print("exception_stops_and_audit_failed", run_exception_and_audit_failed_check())
    print("pipeline_order_explicit", run_pipeline_order_check())


if __name__ == "__main__":
    main()
