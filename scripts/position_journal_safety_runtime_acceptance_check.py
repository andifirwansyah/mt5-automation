"""Acceptance checks for position monitor, journal, kill switch, runtime updater."""

from __future__ import annotations

import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.domain.enums import ExecutionDecisionStatus, OrderExecutionStatus, SignalDirection
from src.domain.models.execution_decision import ExecutionDecision
from src.domain.models.order_result import OrderResult
from src.domain.models.signal import SignalContract
from src.engines.kill_switch_monitor import KillSwitchMonitor
from src.engines.position_monitor import PositionMonitor
from src.engines.runtime_state_updater import RuntimeStateUpdater
from src.engines.trade_journal_engine import TradeJournalEngine
from src.infrastructure.database.models import Position, PositionSnapshot, TradeJournal
from src.infrastructure.database.session import SessionLocal
from src.pipeline.trading_context import TradingContext
from src.repositories.account_repository import AccountRepository
from src.repositories.bot_repository import BotRepository
from src.repositories.journal_repository import JournalRepository
from src.repositories.market_repository import MarketRepository
from src.repositories.position_repository import PositionRepository
from src.repositories.safety_repository import SafetyRepository
from src.services.bot_runtime_service import BotRuntimeService
from src.services.position_sync_service import PositionSyncService
from src.services.runtime_state_service import RuntimeStateService
from src.services.trade_lifecycle_service import TradeLifecycleService


class FakePositionClient:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def get_open_positions(self, symbol: str | None = None) -> list[dict]:
        return list(self.rows)


def candle_context(symbol: str = "XAUUSD") -> TradingContext:
    return TradingContext.from_candle_event(
        {
            "symbol": symbol,
            "timeframe": "M5",
            "candle_time": datetime.now(timezone.utc).isoformat(),
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "tick_volume": 1,
        }
    )


def main() -> None:
    session = SessionLocal()
    try:
        bot_repo = BotRepository(session)
        runtime = BotRuntimeService(bot_repo)
        bot = runtime.register_bot_instance("pjsr-ac", socket.gethostname(), 99992, {"scope": "acceptance"})
        runtime.mark_running(bot.id)

        account_repo = AccountRepository(session)
        market_repo = MarketRepository(session)
        position_repo = PositionRepository(session)
        journal_repo = JournalRepository(session)
        safety_repo = SafetyRepository(session)

        account = account_repo.get_or_create_trading_account(
            account_number=f"ACC-{int(datetime.now(timezone.utc).timestamp())}",
            account_name="AC Test",
            broker_server="Demo",
            base_currency="USD",
            leverage=500,
        )
        session.commit()

        # Position monitor: create + update
        fake = FakePositionClient(
            [
                {
                    "ticket": 222001,
                    "symbol": "XAUUSD",
                    "type": 0,
                    "volume": 0.1,
                    "price_open": 2300.0,
                    "sl": 2298.0,
                    "tp": 2304.0,
                    "price_current": 2301.0,
                    "profit": 10.0,
                    "time": int(datetime.now(timezone.utc).timestamp()),
                    "swap": 0.0,
                    "commission": 0.0,
                }
            ]
        )
        monitor = PositionMonitor(
            position_sync_service=PositionSyncService(fake, position_repo, market_repo),
            trade_lifecycle_service=TradeLifecycleService(fake, position_repo, journal_repo),
            position_repository=position_repo,
            account_id=account.id,
        )
        monitor.run(candle_context())

        fake.rows[0]["volume"] = 0.2
        fake.rows[0]["price_current"] = 2302.0
        monitor.run(candle_context())

        pos = session.execute(select(Position).where(Position.mt5_position_ticket == 222001)).scalar_one_or_none()
        open_positions_saved_and_updated = pos is not None and float(pos.volume_lot) == 0.2
        snapshots = session.execute(select(PositionSnapshot).where(PositionSnapshot.position_id == pos.id)).scalars().all() if pos else []
        position_snapshots_saved = len(snapshots) >= 1

        # Trade journal records reject + execution
        journal_engine = TradeJournalEngine(journal_repo)
        ctx_reject = candle_context()
        ctx_reject.reject("TEST_REJECT", {"message": "reject"})
        journal_engine.run(ctx_reject)

        ctx_exec = candle_context()
        ctx_exec.execution_decision = ExecutionDecision(status=ExecutionDecisionStatus.APPROVE_AUTO, details={"msg": "ok"})
        ctx_exec.order_result = OrderResult(
            status=OrderExecutionStatus.FILLED,
            dry_run=False,
            submitted_at=datetime.now(timezone.utc),
            order_ticket=999111,
            request_payload={"r": 1},
            response_payload={"s": 2},
        )
        journal_engine.run(ctx_exec)

        journals = session.execute(
            select(TradeJournal).where(TradeJournal.journal_type.in_(["SIGNAL_REJECTION", "EXECUTION_DECISION", "ORDER_EXECUTION"]))
        ).scalars().all()
        trade_journal_records_reject_and_execution = len(journals) >= 2

        # Kill switch block
        safety_repo.activate_kill_switch(reason="manual", activated_by="test")
        safety_repo.session.commit()
        ks_engine = KillSwitchMonitor(safety_repo)
        ks_ctx = ks_engine.run(candle_context())
        kill_switch_blocks_pipeline = ks_ctx.rejected and ks_ctx.rejection_reason == "KILL_SWITCH_ACTIVE"

        # Runtime state updater
        updater = RuntimeStateUpdater(RuntimeStateService(bot_repo, bot.id))
        state_ctx = candle_context()
        state_ctx.signal_contract = SignalContract(
            symbol="XAUUSD",
            timeframe="M5",
            direction=SignalDirection.BUY,
            entry_price=2300.0,
            stop_loss=2298.0,
            take_profit=2304.0,
            lot_size=0.1,
            confidence=0.8,
            generated_at=datetime.now(timezone.utc),
            strategy_code="EMA_ATR_TREND",
            metadata={"signal_id": "sig-123"},
        )
        state_ctx.order_result = OrderResult(status=OrderExecutionStatus.FILLED, dry_run=False, order_ticket=123456)
        updater.run(state_ctx)

        state_service = RuntimeStateService(bot_repo, bot.id)
        runtime_state_updated_after_cycle = (
            state_service.get_last_processed_candle("XAUUSD", "M5") is not None
            and str(state_service.get_state("last_signal_id")) == "sig-123"
            and str(state_service.get_state("last_order_id")) == "123456"
            and str(state_service.get_state("last_cycle_status")) in {"SUCCESS", "REJECTED"}
        )

        print("open_positions_saved_and_updated", open_positions_saved_and_updated)
        print("position_snapshots_saved", position_snapshots_saved)
        print("trade_journal_records_reject_and_execution", trade_journal_records_reject_and_execution)
        print("kill_switch_blocks_pipeline", kill_switch_blocks_pipeline)
        print("runtime_state_updated_after_cycle", runtime_state_updated_after_cycle)
    finally:
        session.close()


if __name__ == "__main__":
    main()
