"""Runtime entrypoint that wires all production components."""

from __future__ import annotations

import socket
import time
import uuid

from loguru import logger
from sqlalchemy import text

from src.config.logging_config import setup_logging
from src.config.settings import get_settings
from src.engines import (
    ApprovalEngine,
    BrokerHealthCheck,
    DataCollectorEngine,
    DataQualityGuard,
    ExecutionEngine,
    ExecutionGate,
    HistoricalEdgeValidator,
    KillSwitchMonitor,
    MarketDataIngestionEngine,
    MarketEventFilter,
    MarketRegimeEngine,
    MT5ListenerEngine,
    PreTradeSimulation,
    RiskEngine,
    RuntimeStateUpdater,
    SignalContractBuilder,
    SignalValidator,
    StrategyEngine,
    StrategyFeedbackLoop,
    StrategySelector,
    TradeJournalEngine,
    PerformanceAnalyzer,
)
from src.infrastructure.database.session import SessionLocal
from src.infrastructure.mt5 import MT5AccountClient, MT5Connection, MT5HealthClient, MT5MarketData, MT5OrderExecutor, MT5PositionClient
from src.orchestrators.performance_orchestrator import PerformanceOrchestrator
from src.orchestrators.position_orchestrator import PositionOrchestrator
from src.orchestrators.recovery_orchestrator import RecoveryOrchestrator
from src.orchestrators.trading_orchestrator import TradingOrchestrator
from src.pipeline.trading_pipeline import build_trading_pipeline
from src.repositories import (
    AccountRepository,
    BotRepository,
    ExecutionRepository,
    JournalRepository,
    MarketRepository,
    PerformanceRepository,
    PositionRepository,
    RegimeRepository,
    RiskRepository,
    SafetyRepository,
    SignalRepository,
    StrategyRepository,
)
from src.services import (
    AccountSnapshotService,
    BotRuntimeService,
    CandleService,
    EngineAuditService,
    HeartbeatService,
    PositionSyncService,
    RejectionJournalService,
    RuntimeRecoveryService,
    RuntimeStateService,
    TradeLifecycleService,
)


def main() -> None:
    settings = get_settings()
    setup_logging(settings)

    logger.info("Starting bot worker runtime wiring")

    trading_session = SessionLocal()
    heartbeat_session = SessionLocal()
    performance_session = SessionLocal()

    heartbeat_service: HeartbeatService | None = None
    listener: MT5ListenerEngine | None = None
    performance_orchestrator: PerformanceOrchestrator | None = None
    mt5_connection: MT5Connection | None = None

    bot_runtime_service: BotRuntimeService | None = None
    bot_instance_id: uuid.UUID | None = None
    had_error = False

    try:
        # 1) Startup checks
        trading_session.execute(text("SELECT 1"))

        mt5_connection = MT5Connection(
            path=settings.mt5_path,
            login=settings.mt5_login,
            password=settings.mt5_password,
            server=settings.mt5_server,
            timeout_ms=settings.mt5_timeout_ms,
        )
        if not mt5_connection.connect():
            raise RuntimeError(f"MT5 connect failed: {mt5_connection.get_last_error()}")

        # repositories/services (trading session)
        bot_repo = BotRepository(trading_session)
        market_repo = MarketRepository(trading_session)
        account_repo = AccountRepository(trading_session)
        regime_repo = RegimeRepository(trading_session)
        strategy_repo = StrategyRepository(trading_session)
        signal_repo = SignalRepository(trading_session)
        risk_repo = RiskRepository(trading_session)
        execution_repo = ExecutionRepository(trading_session)
        position_repo = PositionRepository(trading_session)
        safety_repo = SafetyRepository(trading_session)
        journal_repo = JournalRepository(trading_session)

        candle_service = CandleService(market_repo)
        account_snapshot_service = AccountSnapshotService(account_repo)
        trade_lifecycle_service = TradeLifecycleService(MT5PositionClient(), position_repo, journal_repo)
        position_sync_service = PositionSyncService(MT5PositionClient(), position_repo, market_repo)

        bot_runtime_service = BotRuntimeService(bot_repo)
        bot_instance = bot_runtime_service.register_bot_instance(
            instance_name="bot-worker",
            host_name=socket.gethostname(),
            process_id=0,
            metadata={
                "symbol": settings.trading_symbol,
                "timeframe": settings.trading_timeframe,
                "dry_run": settings.dry_run,
            },
        )
        bot_instance_id = bot_instance.id
        bot_runtime_service.mark_running(bot_instance_id)

        runtime_state_service = RuntimeStateService(bot_repo, bot_instance_id)
        rejection_journal_service = RejectionJournalService(journal_repo)

        # MT5 clients
        market_data = MT5MarketData()
        account_client = MT5AccountClient()
        position_client = MT5PositionClient()
        order_executor = MT5OrderExecutor(settings)
        health_client = MT5HealthClient(mt5_connection, market_data, account_client)

        # resolve trading account id for position sync/recovery
        account_data = account_client.to_domain_account_data() or {
            "account_number": str(settings.mt5_login),
            "account_name": "MT5 Account",
            "broker_server": settings.mt5_server,
            "base_currency": "USD",
            "leverage": 0,
        }
        trading_account = account_repo.get_or_create_trading_account(
            account_number=account_data["account_number"],
            account_name=account_data["account_name"],
            broker_server=account_data["broker_server"],
            base_currency=account_data["base_currency"],
            leverage=int(account_data.get("leverage", 0)),
            metadata={"source": "mt5_startup"},
        )
        trading_session.commit()

        # 2) Recovery
        recovery = RecoveryOrchestrator(
            runtime_state_service=runtime_state_service,
            position_sync_service=position_sync_service,
            safety_repository=safety_repo,
            account_id=trading_account.id,
            runtime_recovery_service=RuntimeRecoveryService(
                runtime_state_service=runtime_state_service,
                position_sync_service=position_sync_service,
                safety_repository=safety_repo,
                bot_repository=bot_repo,
                execution_repository=execution_repo,
                account_id=trading_account.id,
            ),
        )
        recovery.run_startup()

        # 3) Heartbeat
        heartbeat_repo = BotRepository(heartbeat_session)
        heartbeat_service = HeartbeatService(
            heartbeat_repo,
            bot_instance_id,
            interval_seconds=settings.heartbeat_interval_seconds,
        )
        heartbeat_service.start()

        # engines
        kill_switch_monitor = KillSwitchMonitor(safety_repo, settings)
        data_collector = DataCollectorEngine(
            market_data=market_data,
            account_client=account_client,
            position_client=position_client,
        )
        ingestion_engine = MarketDataIngestionEngine(market_repo, account_repo, candle_service, account_snapshot_service)
        data_quality = DataQualityGuard(market_repo, candle_service, max_spread=settings.max_spread)
        market_event = MarketEventFilter(market_repo)
        regime_engine = MarketRegimeEngine(regime_repo)
        strategy_selector = StrategySelector(strategy_repo)
        strategy_engine = StrategyEngine()
        signal_builder = SignalContractBuilder(signal_repo, strategy_repo)
        signal_validator = SignalValidator(signal_repo, position_repo, settings)
        edge_validator = HistoricalEdgeValidator(signal_repo, settings)
        risk_engine = RiskEngine(risk_repo, settings)
        pretrade_engine = PreTradeSimulation(risk_repo, settings)
        broker_health = BrokerHealthCheck(health_client, execution_repo, settings)
        execution_gate = ExecutionGate(execution_repo, safety_repo, settings)
        approval_engine = ApprovalEngine(execution_repo, settings)
        execution_engine = ExecutionEngine(execution_repo, safety_repo, order_executor, settings)
        trade_journal_engine = TradeJournalEngine(journal_repo)
        runtime_state_updater = RuntimeStateUpdater(runtime_state_service)

        steps = build_trading_pipeline(
            {
                "KillSwitchMonitor": kill_switch_monitor,
                "DataCollectorEngine": data_collector,
                "MarketDataIngestionEngine": ingestion_engine,
                "DataQualityGuard": data_quality,
                "MarketEventFilter": market_event,
                "MarketRegimeEngine": regime_engine,
                "StrategySelector": strategy_selector,
                "StrategyEngine": strategy_engine,
                "SignalContractBuilder": signal_builder,
                "SignalValidator": signal_validator,
                "HistoricalEdgeValidator": edge_validator,
                "RiskEngine": risk_engine,
                "PreTradeSimulation": pretrade_engine,
                "BrokerHealthCheck": broker_health,
                "ExecutionGate": execution_gate,
                "ApprovalEngine": approval_engine,
                "ExecutionEngine": execution_engine,
                "TradeJournalEngine": trade_journal_engine,
                "RuntimeStateUpdater": runtime_state_updater,
            }
        )

        engine_audit = EngineAuditService(bot_repo, bot_instance_id)
        trading_orchestrator = TradingOrchestrator(
            steps=steps,
            engine_audit_service=engine_audit,
            journal_engine=trade_journal_engine,
            rejection_journal_service=rejection_journal_service,
        )

        position_orchestrator = PositionOrchestrator(position_sync_service, trade_lifecycle_service, position_repo)

        perf_repo = PerformanceRepository(performance_session)
        performance_orchestrator = PerformanceOrchestrator(
            performance_analyzer=PerformanceAnalyzer(perf_repo),
            strategy_feedback_loop=StrategyFeedbackLoop(perf_repo, settings),
        )
        performance_orchestrator.start(interval_seconds=settings.performance_interval_seconds)

        last_position_sync = {"ts": 0.0}

        def on_new_candle(candle_event: dict) -> None:
            trading_orchestrator.run_cycle(candle_event)

        def on_tick(_tick: dict) -> None:
            now = time.time()
            if now - last_position_sync["ts"] < settings.position_sync_interval_seconds:
                return
            last_position_sync["ts"] = now
            position_orchestrator.run_cycle(account_id=trading_account.id)

        # 4) Listener loop
        listener = MT5ListenerEngine(
            market_data=market_data,
            symbol=settings.trading_symbol,
            timeframe=settings.trading_timeframe,
            interval_seconds=settings.listener_interval_seconds,
            on_new_candle=on_new_candle,
            on_tick=on_tick,
        )
        listener.start()

        logger.info("Bot worker running. Press Ctrl+C to stop.")
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, stopping bot worker")
    except Exception as exc:
        had_error = True
        logger.exception("Bot worker crashed: {}", exc)
        if bot_runtime_service is not None and bot_instance_id is not None:
            try:
                bot_runtime_service.mark_error(bot_instance_id=bot_instance_id, error_message=str(exc))
            except Exception:
                logger.exception("Failed to mark bot status error")
    finally:
        # 8) Graceful shutdown
        if listener is not None:
            listener.stop()
        if heartbeat_service is not None:
            heartbeat_service.stop()
        if performance_orchestrator is not None:
            performance_orchestrator.stop()

        if not had_error and bot_runtime_service is not None and bot_instance_id is not None:
            try:
                bot_runtime_service.mark_stopped(bot_instance_id=bot_instance_id)
            except Exception:
                logger.exception("Failed to mark bot status stopped")

        if mt5_connection is not None:
            try:
                mt5_connection.shutdown()
            except Exception:
                logger.exception("Failed to shutdown MT5")

        trading_session.close()
        heartbeat_session.close()
        performance_session.close()


if __name__ == "__main__":
    main()
