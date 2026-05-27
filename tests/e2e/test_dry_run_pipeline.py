from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from src.config.settings import get_settings
from src.domain.enums import ExecutionDecisionStatus, OrderExecutionStatus
from src.domain.models.order_result import OrderResult
from src.engines.approval_engine import ApprovalEngine
from src.engines.broker_health_check import BrokerHealthCheck
from src.engines.data_quality_guard import DataQualityGuard
from src.engines.execution_engine import ExecutionEngine
from src.engines.execution_gate import ExecutionGate
from src.engines.historical_edge_validator import HistoricalEdgeValidator
from src.engines.market_data_ingestion_engine import MarketDataIngestionEngine
from src.engines.market_event_filter import MarketEventFilter
from src.engines.market_regime_engine import MarketRegimeEngine
from src.engines.pre_trade_simulation import PreTradeSimulation
from src.engines.risk_engine import RiskEngine
from src.engines.signal_contract_builder import SignalContractBuilder
from src.engines.signal_validator import SignalValidator
from src.engines.strategy_engine import StrategyEngine
from src.engines.strategy_selector import StrategySelector
from src.engines.trade_journal_engine import TradeJournalEngine
from src.infrastructure.database.models import Strategy, TradeJournal
from src.orchestrators.trading_orchestrator import TradingOrchestrator
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories.account_repository import AccountRepository
from src.repositories.bot_repository import BotRepository
from src.repositories.execution_repository import ExecutionRepository
from src.repositories.journal_repository import JournalRepository
from src.repositories.market_repository import MarketRepository
from src.repositories.position_repository import PositionRepository
from src.repositories.regime_repository import RegimeRepository
from src.repositories.risk_repository import RiskRepository
from src.repositories.safety_repository import SafetyRepository
from src.repositories.signal_repository import SignalRepository
from src.repositories.strategy_repository import StrategyRepository
from src.services.account_snapshot_service import AccountSnapshotService
from src.services.candle_service import CandleService
from src.services.engine_audit_service import EngineAuditService


def _build_rates_dataframe(count: int = 80, start_price: float = 2200.0):
    rows: list[dict] = []
    now = datetime.now(timezone.utc).replace(microsecond=0)
    for i in range(count):
        t = now - timedelta(minutes=(count - i) * 5)
        o = start_price + (i * 2.0)
        c = o + 1.0
        h = c + 3.0
        l = o - 3.0
        rows.append(
            {
                "time": t,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "tick_volume": 100 + i,
                "spread": 8,
                "real_volume": 0,
            }
        )
    import pandas as pd

    return pd.DataFrame(rows)


class MockDataCollectorStep(PipelineStep):
    @property
    def name(self) -> str:
        return "MockDataCollectorStep"

    def run(self, context: TradingContext) -> TradingContext:
        rates = _build_rates_dataframe(count=90, start_price=2200.0)
        context.ingestion_result = {
            "source": "mock_data_collector",
            "rates_by_timeframe": {"M5": rates},
            "tick": {
                "time": int(datetime.now(timezone.utc).timestamp()),
                "bid": float(rates.iloc[-1]["close"] - 0.2),
                "ask": float(rates.iloc[-1]["close"] + 0.2),
                "last": float(rates.iloc[-1]["close"]),
            },
            "account_info": {
                "login": 12345,
                "name": "demo",
                "server": "demo-server",
                "currency": "USD",
                "leverage": 100,
                "balance": 10000.0,
                "equity": 10000.0,
                "margin": 100.0,
                "margin_free": 9900.0,
                "margin_level": 500.0,
                "profit": 0.0,
                "trade_allowed": True,
            },
            "open_positions": [],
            "symbol_info": {
                "volume_min": 0.01,
                "volume_max": 5.0,
                "volume_step": 0.01,
                "trade_contract_size": 100.0,
            },
        }
        return context


class FakeHealthAccountClient:
    @staticmethod
    def get_account_info() -> dict:
        return {"trade_allowed": True, "margin_free": 9900.0}


class FakeHealthClient:
    def __init__(self) -> None:
        self.account_client = FakeHealthAccountClient()

    @staticmethod
    def check_connection() -> bool:
        return True

    @staticmethod
    def check_trade_allowed() -> bool:
        return True

    @staticmethod
    def check_symbol_trade_allowed(_symbol: str) -> bool:
        return True

    @staticmethod
    def check_spread(_symbol: str) -> float:
        return 8.0

    @staticmethod
    def check_margin_level() -> float:
        return 500.0


class FakeOrderExecutor:
    def __init__(self) -> None:
        self.send_called = 0

    @staticmethod
    def build_market_order_request(signal, risk_plan) -> dict:
        return {
            "symbol": signal.symbol,
            "volume": risk_plan.lot_size,
            "sl": risk_plan.stop_loss,
            "tp": risk_plan.take_profit,
        }

    @staticmethod
    def order_check(_request: dict) -> dict:
        return {"retcode": 10009, "comment": "OK"}

    def send_market_order(self, *_args, **_kwargs) -> OrderResult:
        self.send_called += 1
        raise AssertionError("send_market_order must not be called in DRY_RUN e2e")


def test_e2e_dry_run_orchestrator_pipeline(db_session, unique_suffix: str) -> None:
    market_repo = MarketRepository(db_session)
    account_repo = AccountRepository(db_session)
    bot_repo = BotRepository(db_session)
    strategy_repo = StrategyRepository(db_session)
    signal_repo = SignalRepository(db_session)
    position_repo = PositionRepository(db_session)
    risk_repo = RiskRepository(db_session)
    execution_repo = ExecutionRepository(db_session)
    safety_repo = SafetyRepository(db_session)
    regime_repo = RegimeRepository(db_session)
    journal_repo = JournalRepository(db_session)

    safety_repo.deactivate_kill_switch(deactivated_by="pytest", details={"reason": "e2e pre-clean"})
    db_session.commit()

    strategy = db_session.execute(select(Strategy).where(Strategy.code == "EMA_ATR_TREND")).scalar_one_or_none()
    if strategy is None:
        strategy = Strategy(code="EMA_ATR_TREND", name="EMA ATR Trend", description="Trend", is_active=True, metadata_json={})
        db_session.add(strategy)
        db_session.commit()

    bot = bot_repo.create_bot_instance(
        instance_name=f"e2e-dry-run-{unique_suffix}",
        host_name="localhost",
        process_id=77777,
        status="running",
        metadata={"scope": "e2e"},
    )
    db_session.commit()

    candle_service = CandleService(market_repo)
    account_snapshot_service = AccountSnapshotService(account_repo)
    engine_audit = EngineAuditService(bot_repository=bot_repo, bot_instance_id=bot.id)

    settings = get_settings().model_copy(update={"auto_trade": True, "dry_run": True, "approval_required": False})
    fake_order_executor = FakeOrderExecutor()

    steps: list[PipelineStep] = [
        MockDataCollectorStep(),
        MarketDataIngestionEngine(
            market_repository=market_repo,
            account_repository=account_repo,
            candle_service=candle_service,
            account_snapshot_service=account_snapshot_service,
        ),
        DataQualityGuard(market_repository=market_repo, candle_service=candle_service),
        MarketEventFilter(market_repository=market_repo),
        MarketRegimeEngine(regime_repository=regime_repo),
        StrategySelector(strategy_repository=strategy_repo),
        StrategyEngine(),
        SignalContractBuilder(signal_repository=signal_repo, strategy_repository=strategy_repo),
        SignalValidator(signal_repository=signal_repo, position_repository=position_repo, settings=settings),
        HistoricalEdgeValidator(signal_repository=signal_repo, settings=settings),
        RiskEngine(risk_repository=risk_repo, settings=settings),
        PreTradeSimulation(risk_repository=risk_repo, settings=settings),
        BrokerHealthCheck(health_client=FakeHealthClient(), execution_repository=execution_repo, settings=settings),
        ExecutionGate(execution_repository=execution_repo, safety_repository=safety_repo, settings=settings),
        ApprovalEngine(execution_repository=execution_repo, settings=settings),
        ExecutionEngine(
            execution_repository=execution_repo,
            safety_repository=safety_repo,
            order_executor=fake_order_executor,
            settings=settings,
        ),
        TradeJournalEngine(journal_repository=journal_repo),
    ]

    orchestrator = TradingOrchestrator(steps=steps, engine_audit_service=engine_audit)
    midday = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    event = {
        "symbol": f"XAUUSD_E2E_{unique_suffix}",
        "timeframe": "M5",
        "candle_time": midday.isoformat(),
        "open": 2300.0,
        "high": 2302.0,
        "low": 2299.0,
        "close": 2301.0,
        "tick_volume": 123,
    }

    result = orchestrator.run_cycle(event)

    assert result.rejected is False
    assert result.execution_decision is not None
    assert result.execution_decision.status == ExecutionDecisionStatus.DRY_RUN
    assert result.order_result is not None
    assert result.order_result.status == OrderExecutionStatus.DRY_RUN
    assert fake_order_executor.send_called == 0

    journals = db_session.execute(select(TradeJournal).where(TradeJournal.trace_id == result.trace_id)).scalars().all()
    assert len(journals) >= 1
