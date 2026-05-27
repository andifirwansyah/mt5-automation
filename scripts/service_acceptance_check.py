"""Smoke check for service layer acceptance criteria."""

from __future__ import annotations

import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.infrastructure.database.models import EngineRun
from src.infrastructure.database.session import SessionLocal
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories import BotRepository
from src.services import BotRuntimeService, EngineAuditService, HeartbeatService, RuntimeStateService


class DummyStep(PipelineStep):
    @property
    def name(self) -> str:
        return "DUMMY_STEP"

    def run(self, context: TradingContext) -> TradingContext:
        return context


def main() -> None:
    session = SessionLocal()
    try:
        bot_repo = BotRepository(session)
        runtime = BotRuntimeService(bot_repo)
        bot = runtime.register_bot_instance(
            instance_name="bot-worker-test",
            host_name=socket.gethostname(),
            process_id=99999,
            metadata={"source": "service_acceptance"},
        )
        runtime.mark_running(bot.id)

        heartbeat = HeartbeatService(bot_repo, bot.id, interval_seconds=0.5)
        heartbeat.start()
        time.sleep(1.2)
        heartbeat.stop()

        state = bot_repo.get_runtime_state(bot.id)
        print("bot_registered", bot.id is not None)
        print("heartbeat_updated", isinstance((state.details or {}).get("last_heartbeat_at"), str))

        audit = EngineAuditService(bot_repo, bot.id)
        context = TradingContext.from_candle_event(
            {
                "symbol": "XAUUSD",
                "timeframe": "M5",
                "candle_time": datetime.now(timezone.utc).isoformat(),
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
                "tick_volume": 10,
            }
        )
        audit.run_and_audit(DummyStep(), context)

        runs = session.execute(select(EngineRun).where(EngineRun.trace_id == context.trace_id)).scalars().all()
        print("engine_audit_saved", len(runs) >= 2)

        runtime_state = RuntimeStateService(bot_repo, bot.id)
        candle_time = datetime.now(timezone.utc)
        runtime_state.set_last_processed_candle("XAUUSD", "M5", candle_time)
        loaded = runtime_state.get_last_processed_candle("XAUUSD", "M5")
        print("runtime_state_candle_saved", loaded is not None)
    finally:
        session.close()


if __name__ == "__main__":
    main()
