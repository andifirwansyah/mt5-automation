"""Acceptance checks for signal pipeline engines."""

from __future__ import annotations

import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.domain.enums import SignalDirection
from src.domain.models.signal import RawSignal
from src.domain.models.strategy_selection import StrategySelectionResult
from src.engines.historical_edge_validator import HistoricalEdgeValidator
from src.engines.signal_contract_builder import SignalContractBuilder
from src.engines.signal_validator import SignalValidator
from src.infrastructure.database.models import HistoricalEdgeValidation, Signal, SignalValidation, Strategy
from src.infrastructure.database.session import SessionLocal
from src.pipeline.trading_context import TradingContext
from src.repositories.bot_repository import BotRepository
from src.repositories.market_repository import MarketRepository
from src.repositories.position_repository import PositionRepository
from src.repositories.signal_repository import SignalRepository
from src.repositories.strategy_repository import StrategyRepository
from src.services.bot_runtime_service import BotRuntimeService


def main() -> None:
    session = SessionLocal()
    try:
        bot_repo = BotRepository(session)
        runtime = BotRuntimeService(bot_repo)
        bot = runtime.register_bot_instance(
            instance_name="signal-ac-test",
            host_name=socket.gethostname(),
            process_id=99996,
            metadata={"scope": "signal_pipeline_acceptance"},
        )
        runtime.mark_running(bot.id)

        market_repo = MarketRepository(session)
        strategy_repo = StrategyRepository(session)
        signal_repo = SignalRepository(session)
        position_repo = PositionRepository(session)

        symbol = market_repo.get_or_create_symbol(name=f"XAUUSD_SIGNAL_AC_{int(datetime.now(timezone.utc).timestamp())}")
        timeframe = market_repo.get_or_create_timeframe(code="M5", minutes=5, description="M5")

        strategy = session.execute(select(Strategy).where(Strategy.code == "EMA_ATR_TREND")).scalar_one_or_none()
        if strategy is None:
            strategy = Strategy(
                code="EMA_ATR_TREND",
                name="EMA ATR Trend",
                description="Trend following",
                is_active=True,
                metadata_json={},
            )
            session.add(strategy)
            session.flush()
        session.commit()

        builder = SignalContractBuilder(signal_repository=signal_repo, strategy_repository=strategy_repo)
        validator = SignalValidator(signal_repository=signal_repo, position_repository=position_repo)
        edge_validator = HistoricalEdgeValidator(signal_repository=signal_repo)

        signal_time = datetime.now(timezone.utc).replace(microsecond=0)

        # First signal context
        context_1 = TradingContext.from_candle_event(
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
        context_1.ingestion_result = {
            "symbol_id": symbol.id,
            "timeframe_ids": {"M5": timeframe.id},
        }
        context_1.raw_signal = RawSignal(
            direction=SignalDirection.BUY,
            confidence=0.8,
            entry_price=2301.0,
            stop_loss=2298.0,
            take_profit=2306.0,
            generated_at=signal_time,
            features={"test": True},
            metadata={},
        )
        context_1.strategy_selection = StrategySelectionResult(
            strategy_code="EMA_ATR_TREND",
            strategy_name="EMA ATR Trend",
            score=0.8,
            reason="acceptance test",
            config={"lot_size": 0.1},
            details={"strategy_id": str(strategy.id)},
        )

        context_1 = builder.run(context_1)
        raw_to_contract_ok = context_1.signal_contract is not None

        signal_id_1 = context_1.signal_contract.metadata.get("signal_id") if context_1.signal_contract else None
        signal_saved = False
        if signal_id_1:
            row = session.get(Signal, signal_id_1)
            signal_saved = row is not None

        context_1 = validator.run(context_1)
        signal_validation_saved = False
        if signal_id_1:
            validations = session.execute(select(SignalValidation).where(SignalValidation.signal_id == signal_id_1)).scalars().all()
            signal_validation_saved = len(validations) >= 1

        # Duplicate signal context (same candle time)
        context_2 = TradingContext.from_candle_event(
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
        context_2.ingestion_result = {
            "symbol_id": symbol.id,
            "timeframe_ids": {"M5": timeframe.id},
        }
        context_2.raw_signal = RawSignal(
            direction=SignalDirection.BUY,
            confidence=0.75,
            entry_price=2301.0,
            stop_loss=2298.0,
            take_profit=2306.0,
            generated_at=signal_time,
            features={"test": "duplicate"},
            metadata={},
        )
        context_2.strategy_selection = StrategySelectionResult(
            strategy_code="EMA_ATR_TREND",
            strategy_name="EMA ATR Trend",
            score=0.75,
            reason="duplicate acceptance test",
            config={"lot_size": 0.1},
            details={"strategy_id": str(strategy.id)},
        )
        context_2 = builder.run(context_2)
        context_2 = validator.run(context_2)
        duplicate_blocked = context_2.rejected and context_2.rejection_reason == "SIGNAL_VALIDATION_FAILED"

        # Historical edge check on first signal (no history expected)
        context_1 = edge_validator.run(context_1)
        edge_row = session.execute(
            select(HistoricalEdgeValidation).where(HistoricalEdgeValidation.signal_id == signal_id_1)
        ).scalar_one_or_none()

        edge_no_fake = (
            context_1.historical_edge is not None
            and context_1.historical_edge.sample_size == 0
            and context_1.historical_edge.win_rate == 0.0
            and edge_row is not None
            and edge_row.sample_size == 0
            and float(edge_row.win_rate) == 0.0
        )

        print("rawsignal_to_contract", raw_to_contract_ok)
        print("signal_saved_to_db", signal_saved)
        print("signal_validation_saved", signal_validation_saved)
        print("duplicate_signal_blocked", duplicate_blocked)
        print("historical_edge_no_fake_data", edge_no_fake)
    finally:
        session.close()


if __name__ == "__main__":
    main()
