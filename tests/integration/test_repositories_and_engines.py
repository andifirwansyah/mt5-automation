from __future__ import annotations

import socket
import uuid
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import select

from src.engines.market_data_ingestion_engine import MarketDataIngestionEngine
from src.infrastructure.database.models import BotInstance, Candle, EngineRun, TradeJournal
from src.orchestrators.trading_orchestrator import TradingOrchestrator
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories.account_repository import AccountRepository
from src.repositories.bot_repository import BotRepository
from src.repositories.journal_repository import JournalRepository
from src.repositories.market_repository import MarketRepository
from src.services.account_snapshot_service import AccountSnapshotService
from src.services.bot_runtime_service import BotRuntimeService
from src.services.candle_service import CandleService
from src.services.engine_audit_service import EngineAuditService
from src.services.rejection_journal_service import RejectionJournalService


def test_database_repositories_create_read_basic_entities(db_session, unique_suffix: str) -> None:
    bot_repo = BotRepository(db_session)
    runtime = BotRuntimeService(bot_repo)

    bot = runtime.register_bot_instance(
        instance_name=f"it-bot-{unique_suffix}",
        host_name=socket.gethostname(),
        process_id=99901,
        metadata={"scope": "integration_test"},
    )
    runtime.mark_running(bot.id)

    market_repo = MarketRepository(db_session)
    symbol = market_repo.get_or_create_symbol(name=f"XAUUSD_IT_{unique_suffix}")
    timeframe = market_repo.get_or_create_timeframe(code=f"M{5 + int(unique_suffix[:2], 16) % 30}", minutes=5)
    market_repo.upsert_candle(
        symbol_id=symbol.id,
        timeframe_id=timeframe.id,
        open_time=datetime.now(timezone.utc),
        open_price=2300.0,
        high_price=2302.0,
        low_price=2299.0,
        close_price=2301.0,
        tick_volume=100,
    )
    db_session.commit()

    latest_bot = db_session.execute(select(BotInstance).where(BotInstance.id == bot.id)).scalar_one_or_none()
    assert latest_bot is not None
    latest_candles = market_repo.get_latest_candles(symbol_id=symbol.id, timeframe_id=timeframe.id, limit=1)
    assert len(latest_candles) == 1


def test_market_data_ingestion_saves_candles(db_session, unique_suffix: str) -> None:
    market_repo = MarketRepository(db_session)
    account_repo = AccountRepository(db_session)
    candle_service = CandleService(market_repo)
    account_snapshot_service = AccountSnapshotService(account_repo)
    engine = MarketDataIngestionEngine(
        market_repository=market_repo,
        account_repository=account_repo,
        candle_service=candle_service,
        account_snapshot_service=account_snapshot_service,
    )

    symbol = f"XAUUSD_INGEST_{unique_suffix}"
    event = {
        "symbol": symbol,
        "timeframe": "M5",
        "candle_time": datetime.now(timezone.utc).isoformat(),
        "open": 2300,
        "high": 2302,
        "low": 2299,
        "close": 2301,
        "tick_volume": 10,
    }
    context = TradingContext.from_candle_event(event)

    frame = pd.DataFrame(
        [
            {
                "time": datetime.now(timezone.utc),
                "open": 2300.0,
                "high": 2302.0,
                "low": 2299.0,
                "close": 2301.0,
                "tick_volume": 111,
                "spread": 9,
                "real_volume": 0,
            }
        ]
    )
    context.ingestion_result = {
        "rates_by_timeframe": {"M5": frame},
        "tick": {"time": int(datetime.now(timezone.utc).timestamp()), "bid": 2300.0, "ask": 2300.3},
        "account_info": {
            "login": 12345,
            "name": "demo",
            "server": "demo-server",
            "currency": "USD",
            "leverage": 100,
            "balance": 10000,
            "equity": 10000,
            "margin": 0,
            "margin_free": 10000,
            "margin_level": 0,
            "profit": 0,
        },
    }

    out = engine.run(context)
    assert int(out.ingestion_result["candles_saved"]) >= 1

    symbol_row = market_repo.get_or_create_symbol(name=symbol)
    tf_row = market_repo.get_or_create_timeframe(code="M5", minutes=5)
    candles = db_session.execute(
        select(Candle).where(Candle.symbol_id == symbol_row.id, Candle.timeframe_id == tf_row.id)
    ).scalars().all()
    assert len(candles) >= 1


def test_engine_audit_service_records_engine_run(db_session, unique_suffix: str) -> None:
    class PassStep(PipelineStep):
        @property
        def name(self) -> str:
            return "PASS_STEP_IT"

        def run(self, context: TradingContext) -> TradingContext:
            return context

    bot_repo = BotRepository(db_session)
    bot = bot_repo.create_bot_instance(
        instance_name=f"audit-{unique_suffix}",
        host_name="localhost",
        process_id=88888,
        status="running",
        metadata={"scope": "audit_test"},
    )
    db_session.commit()

    service = EngineAuditService(bot_repository=bot_repo, bot_instance_id=bot.id)
    context = TradingContext.from_candle_event(
        {"symbol": "XAUUSD", "timeframe": "M5", "open": 1, "high": 2, "low": 0.5, "close": 1.2, "tick_volume": 1}
    )
    service.run_and_audit(PassStep(), context)

    rows = db_session.execute(
        select(EngineRun).where(EngineRun.trace_id == context.trace_id, EngineRun.engine_name == "PASS_STEP_IT")
    ).scalars().all()
    assert len(rows) >= 2


def test_all_rejects_are_saved_to_database(db_session, unique_suffix: str) -> None:
    class RejectStep(PipelineStep):
        @property
        def name(self) -> str:
            return "REJECT_IT_STEP"

        def run(self, context: TradingContext) -> TradingContext:
            context.reject("REJECTED_FOR_TEST", {"source": "integration"})
            return context

    bot_repo = BotRepository(db_session)
    journal_repo = JournalRepository(db_session)
    bot = bot_repo.create_bot_instance(
        instance_name=f"reject-journal-{unique_suffix}",
        host_name="localhost",
        process_id=99977,
        status="running",
        metadata={"scope": "reject_journal_test"},
    )
    db_session.commit()

    orchestrator = TradingOrchestrator(
        steps=[RejectStep()],
        engine_audit_service=EngineAuditService(bot_repository=bot_repo, bot_instance_id=bot.id),
        rejection_journal_service=RejectionJournalService(journal_repository=journal_repo),
    )
    context = orchestrator.run_cycle(
        {
            "symbol": "XAUUSD",
            "timeframe": "M5",
            "candle_time": datetime.now(timezone.utc).isoformat(),
            "open": 1,
            "high": 2,
            "low": 0.5,
            "close": 1.5,
            "tick_volume": 1,
        }
    )

    journals = db_session.execute(
        select(TradeJournal).where(TradeJournal.trace_id == context.trace_id, TradeJournal.journal_type == "PIPELINE_REJECTION")
    ).scalars().all()
    assert context.rejected is True
    assert context.rejection_reason == "REJECTED_FOR_TEST"
    assert len(journals) >= 1
