"""Acceptance checks for RiskEngine, PreTradeSimulation, BrokerHealthCheck."""

from __future__ import annotations

import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config.settings import get_settings
from src.domain.enums import MarketRegimeType, SignalDirection
from src.domain.models.market_snapshot import MarketSnapshot
from src.domain.models.regime_result import RegimeResult
from src.domain.models.signal import SignalContract
from src.engines.broker_health_check import BrokerHealthCheck
from src.engines.pre_trade_simulation import PreTradeSimulation
from src.engines.risk_engine import RiskEngine
from src.infrastructure.database.models import BrokerHealthCheck as BrokerHealthCheckModel
from src.infrastructure.database.models import PreTradeSimulation as PreTradeSimulationModel
from src.infrastructure.database.models import RiskAssessment, Strategy
from src.infrastructure.database.session import SessionLocal
from src.pipeline.trading_context import TradingContext
from src.repositories.bot_repository import BotRepository
from src.repositories.execution_repository import ExecutionRepository
from src.repositories.market_repository import MarketRepository
from src.repositories.risk_repository import RiskRepository
from src.repositories.signal_repository import SignalRepository
from src.services.bot_runtime_service import BotRuntimeService


class FakeAccountClient:
    def __init__(self, trade_allowed: bool = True, margin_free: float = 10000.0, margin_level: float = 500.0) -> None:
        self._trade_allowed = trade_allowed
        self._margin_free = margin_free
        self._margin_level = margin_level

    def get_account_info(self) -> dict:
        return {
            "trade_allowed": self._trade_allowed,
            "margin_free": self._margin_free,
            "margin_level": self._margin_level,
        }


class FakeHealthClient:
    def __init__(
        self,
        connected: bool,
        terminal_trade_allowed: bool,
        symbol_trade_allowed: bool,
        spread: float,
        margin_level: float,
        account_client: FakeAccountClient,
    ) -> None:
        self._connected = connected
        self._terminal_trade_allowed = terminal_trade_allowed
        self._symbol_trade_allowed = symbol_trade_allowed
        self._spread = spread
        self._margin_level = margin_level
        self.account_client = account_client

    def check_connection(self) -> bool:
        return self._connected

    def check_trade_allowed(self) -> bool:
        return self._terminal_trade_allowed

    def check_symbol_trade_allowed(self, symbol: str) -> bool:
        return self._symbol_trade_allowed

    def check_spread(self, symbol: str) -> float:
        return self._spread

    def check_margin_level(self) -> float:
        return self._margin_level


def ensure_strategy(session) -> Strategy:
    existing = session.execute(select(Strategy).where(Strategy.code == "EMA_ATR_TREND")).scalar_one_or_none()
    if existing is not None:
        return existing
    strategy = Strategy(code="EMA_ATR_TREND", name="EMA ATR Trend", description="Trend strategy", is_active=True, metadata_json={})
    session.add(strategy)
    session.flush()
    session.commit()
    return strategy


def main() -> None:
    session = SessionLocal()
    try:
        bot_repo = BotRepository(session)
        runtime = BotRuntimeService(bot_repo)
        bot = runtime.register_bot_instance(
            instance_name="risk-ac-test",
            host_name=socket.gethostname(),
            process_id=99995,
            metadata={"scope": "risk_pretrade_health_acceptance"},
        )
        runtime.mark_running(bot.id)

        market_repo = MarketRepository(session)
        signal_repo = SignalRepository(session)
        risk_repo = RiskRepository(session)
        execution_repo = ExecutionRepository(session)

        symbol = market_repo.get_or_create_symbol(name=f"XAUUSD_RISK_AC_{int(datetime.now(timezone.utc).timestamp())}")
        timeframe = market_repo.get_or_create_timeframe(code="M5", minutes=5, description="M5")
        strategy = ensure_strategy(session)
        session.commit()

        signal_time = datetime.now(timezone.utc).replace(microsecond=0)
        signal_row = signal_repo.create_signal(
            trace_id=bot.id,
            symbol_id=symbol.id,
            timeframe_id=timeframe.id,
            strategy_id=strategy.id,
            direction="BUY",
            status="GENERATED",
            signal_time=signal_time,
            entry_price=2300.0,
            stop_loss=2298.0,
            take_profit=2304.0,
            lot_size=0.1,
            confidence=0.8,
            features={},
            raw_payload={},
        )
        session.commit()

        base_context = TradingContext.from_candle_event(
            {
                "symbol": symbol.name,
                "timeframe": "M5",
                "candle_time": signal_time.isoformat(),
                "open": 2300.0,
                "high": 2302.0,
                "low": 2298.0,
                "close": 2301.0,
                "tick_volume": 100,
            }
        )
        base_context.market_snapshot = MarketSnapshot(
            symbol=symbol.name,
            timeframe="M5",
            candle_time=signal_time,
            open_price=2300.0,
            high_price=2302.0,
            low_price=2298.0,
            close_price=2301.0,
            tick_volume=100,
            spread=10,
            features={"account_equity": 10000.0, "account_balance": 10000.0},
        )
        base_context.regime_result = RegimeResult(
            regime=MarketRegimeType.TRENDING_BULLISH,
            confidence=0.8,
            is_tradeable=True,
            features={"atr": 2.0},
        )
        base_context.signal_contract = SignalContract(
            symbol=symbol.name,
            timeframe="M5",
            direction=SignalDirection.BUY,
            entry_price=2300.0,
            stop_loss=2298.0,
            take_profit=2304.0,
            lot_size=0.1,
            confidence=0.8,
            generated_at=signal_time,
            strategy_code="EMA_ATR_TREND",
            metadata={"signal_id": str(signal_row.id), "side": "BUY", "entry_type": "MARKET"},
        )
        base_context.ingestion_result = {
            "symbol_id": symbol.id,
            "timeframe_ids": {"M5": timeframe.id},
            "account_info": {"equity": 10000.0, "balance": 10000.0},
            "symbol_info": {
                "volume_min": 0.01,
                "volume_max": 2.0,
                "volume_step": 0.01,
                "trade_contract_size": 100.0,
            },
        }

        # Risk Engine
        risk_engine = RiskEngine(risk_repository=risk_repo)
        risk_context = risk_engine.run(base_context)

        risk_row = session.execute(select(RiskAssessment).where(RiskAssessment.signal_id == signal_row.id)).scalar_one_or_none()
        risk_saved = risk_row is not None
        sl_tp_present = risk_context.risk_plan is not None and risk_context.risk_plan.stop_loss > 0 and risk_context.risk_plan.take_profit > 0

        lot_in_range = False
        if risk_context.risk_plan is not None:
            lot = float(risk_context.risk_plan.lot_size)
            lot_in_range = 0.01 <= lot <= 2.0

        # PreTrade Simulation (force reject with extreme stress)
        stressed_settings = get_settings().model_copy(update={"pretrade_spread_stress_multiplier": 1000.0})
        pretrade_engine = PreTradeSimulation(risk_repository=risk_repo, settings=stressed_settings)
        pretrade_context = pretrade_engine.run(risk_context)

        pretrade_row = session.execute(select(PreTradeSimulationModel).where(PreTradeSimulationModel.signal_id == signal_row.id)).scalar_one_or_none()
        simulation_rejects_risky = pretrade_row is not None and (not pretrade_row.passed) and pretrade_context.rejected

        # Broker Health check reject: spread tinggi
        health_spread_high = FakeHealthClient(
            connected=True,
            terminal_trade_allowed=True,
            symbol_trade_allowed=True,
            spread=999.0,
            margin_level=500.0,
            account_client=FakeAccountClient(trade_allowed=True, margin_free=10000.0, margin_level=500.0),
        )
        broker_engine_spread = BrokerHealthCheck(health_client=health_spread_high, execution_repository=execution_repo)
        broker_context_spread = TradingContext.from_candle_event(
            {
                "symbol": symbol.name,
                "timeframe": "M5",
                "candle_time": signal_time.isoformat(),
                "open": 1,
                "high": 2,
                "low": 0.5,
                "close": 1.5,
                "tick_volume": 1,
            }
        )
        broker_context_spread.ingestion_result = {"symbol_id": symbol.id}
        broker_context_spread = broker_engine_spread.run(broker_context_spread)

        # Broker Health check reject: disconnect
        health_disconnect = FakeHealthClient(
            connected=False,
            terminal_trade_allowed=True,
            symbol_trade_allowed=True,
            spread=1.0,
            margin_level=500.0,
            account_client=FakeAccountClient(trade_allowed=True, margin_free=10000.0, margin_level=500.0),
        )
        broker_engine_disconnect = BrokerHealthCheck(health_client=health_disconnect, execution_repository=execution_repo)
        broker_context_disconnect = TradingContext.from_candle_event(
            {
                "symbol": symbol.name,
                "timeframe": "M5",
                "candle_time": signal_time.isoformat(),
                "open": 1,
                "high": 2,
                "low": 0.5,
                "close": 1.5,
                "tick_volume": 1,
            }
        )
        broker_context_disconnect.ingestion_result = {"symbol_id": symbol.id}
        broker_context_disconnect = broker_engine_disconnect.run(broker_context_disconnect)

        health_rows = session.execute(select(BrokerHealthCheckModel).where(BrokerHealthCheckModel.symbol_id == symbol.id)).scalars().all()
        broker_health_rejects = (
            len(health_rows) >= 2
            and broker_context_spread.rejected
            and broker_context_disconnect.rejected
            and broker_context_spread.rejection_reason == "BROKER_HEALTH_FAILED"
            and broker_context_disconnect.rejection_reason == "BROKER_HEALTH_FAILED"
        )

        print("risk_assessment_saved", risk_saved)
        print("sl_tp_present", sl_tp_present)
        print("lot_within_volume_bounds", lot_in_range)
        print("simulation_rejects_risky_trade", simulation_rejects_risky)
        print("broker_health_rejects_spread_or_disconnect", broker_health_rejects)
    finally:
        session.close()


if __name__ == "__main__":
    main()
