"""Acceptance checks for performance analyzer and strategy feedback loop."""

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
from src.engines.performance_analyzer import PerformanceAnalyzer
from src.engines.strategy_feedback_loop import StrategyFeedbackLoop
from src.infrastructure.database.models import PerformanceByStrategy, PerformanceDaily, Strategy, StrategyFeedbackEvent
from src.infrastructure.database.session import SessionLocal
from src.repositories.account_repository import AccountRepository
from src.repositories.execution_repository import ExecutionRepository
from src.repositories.market_repository import MarketRepository
from src.repositories.performance_repository import PerformanceRepository
from src.repositories.position_repository import PositionRepository
from src.repositories.signal_repository import SignalRepository


def main() -> None:
    session = SessionLocal()
    try:
        account_repo = AccountRepository(session)
        market_repo = MarketRepository(session)
        signal_repo = SignalRepository(session)
        execution_repo = ExecutionRepository(session)
        position_repo = PositionRepository(session)
        performance_repo = PerformanceRepository(session)

        now = datetime.now(timezone.utc)

        account = account_repo.get_or_create_trading_account(
            account_number=f"PERF-{int(now.timestamp())}",
            account_name="Performance Test",
            broker_server="Demo",
            base_currency="USD",
            leverage=500,
        )
        symbol = market_repo.get_or_create_symbol(name=f"XAUUSD_PERF_{int(now.timestamp())}")
        timeframe = market_repo.get_or_create_timeframe(code="M5", minutes=5)

        strategy = session.execute(select(Strategy).where(Strategy.code == "EMA_ATR_TREND")).scalar_one_or_none()
        if strategy is None:
            strategy = Strategy(
                code="EMA_ATR_TREND",
                name="EMA ATR Trend",
                description="Trend strategy",
                is_active=True,
                metadata_json={},
            )
            session.add(strategy)
            session.flush()

        # Seed closed trades for today
        profits = [120.0, -80.0, 60.0, -40.0, 30.0]
        for idx, p in enumerate(profits):
            signal = signal_repo.create_signal(
                trace_id=account.id,
                symbol_id=symbol.id,
                timeframe_id=timeframe.id,
                strategy_id=strategy.id,
                direction="BUY",
                status="FILLED",
                signal_time=now,
                entry_price=2300.0,
                stop_loss=2298.0,
                take_profit=2304.0,
                lot_size=0.1,
                confidence=0.7,
                features={},
                raw_payload={},
            )
            order = execution_repo.create_execution_order(
                signal_id=signal.id,
                symbol_id=symbol.id,
                side="BUY",
                order_type="MARKET",
                volume_lot=0.1,
                requested_price=2300.0,
                stop_loss=2298.0,
                take_profit=2304.0,
                deviation=20,
                status="FILLED",
                mt5_order_ticket=900000 + idx,
                broker_response={},
                executed_at=now,
            )
            position_repo.upsert_position(
                account_id=account.id,
                symbol_id=symbol.id,
                side="BUY",
                volume_lot=0.1,
                entry_price=2300.0,
                stop_loss=2298.0,
                take_profit=2304.0,
                status="CLOSED",
                opened_at=now,
                execution_order_id=order.id,
                mt5_position_ticket=910000 + idx,
                close_price=2301.0,
                profit=p,
                closed_at=now,
                details={},
            )

        session.commit()

        analyzer = PerformanceAnalyzer(performance_repository=performance_repo)
        analyzer.run_cycle(reference_time=now)

        settings_feedback = get_settings().model_copy(
            update={
                "auto_apply_strategy_feedback": False,
                "feedback_min_trades": 20,
                "feedback_low_win_rate": 0.9,
                "feedback_high_drawdown": 1.0,
            }
        )
        feedback_loop = StrategyFeedbackLoop(performance_repository=performance_repo, settings=settings_feedback)
        feedback_loop.run_cycle()

        daily_rows = session.execute(select(PerformanceDaily).where(PerformanceDaily.account_id == account.id)).scalars().all()
        per_strategy_rows = session.execute(select(PerformanceByStrategy).where(PerformanceByStrategy.strategy_id == strategy.id)).scalars().all()
        feedback_rows = session.execute(select(StrategyFeedbackEvent).where(StrategyFeedbackEvent.strategy_id == strategy.id)).scalars().all()

        session.refresh(strategy)

        daily_performance_calculated = len(daily_rows) >= 1
        per_strategy_calculated = len(per_strategy_rows) >= 1
        strategy_feedback_recorded = len(feedback_rows) >= 1
        no_auto_disable_without_explicit_setting = strategy.is_active is True

        print("daily_performance_calculated", daily_performance_calculated)
        print("performance_per_strategy_calculated", per_strategy_calculated)
        print("strategy_feedback_event_recorded", strategy_feedback_recorded)
        print("no_auto_disable_without_explicit_setting", no_auto_disable_without_explicit_setting)
    finally:
        session.close()


if __name__ == "__main__":
    main()
