"""Acceptance checks for market intelligence engines and strategies."""

from __future__ import annotations

import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from src.domain.enums import MarketRegimeType
from src.domain.models.market_snapshot import MarketSnapshot
from src.domain.models.regime_result import RegimeResult
from src.domain.models.strategy_selection import StrategySelectionResult
from src.engines.market_regime_engine import MarketRegimeEngine
from src.engines.strategy_engine import StrategyEngine
from src.engines.strategy_selector import StrategySelector
from src.infrastructure.database.models import MarketRegime, Strategy
from src.infrastructure.database.session import SessionLocal
from src.pipeline.trading_context import TradingContext
from src.repositories.bot_repository import BotRepository
from src.repositories.market_repository import MarketRepository
from src.repositories.regime_repository import RegimeRepository
from src.repositories.strategy_repository import StrategyRepository
from src.services.bot_runtime_service import BotRuntimeService


class _Row:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


class _ILoc:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def __getitem__(self, item: int) -> _Row:
        return _Row(self._rows[item])


class FakeFrame:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.iloc = _ILoc(rows)

    @property
    def empty(self) -> bool:
        return len(self._rows) == 0

    def __len__(self) -> int:
        return len(self._rows)

    def iterrows(self):
        for idx, row in enumerate(self._rows):
            yield idx, _Row(row)


def ensure_strategy(session, code: str, name: str, description: str) -> Strategy:
    existing = session.execute(select(Strategy).where(Strategy.code == code)).scalar_one_or_none()
    if existing is not None:
        return existing

    strategy = Strategy(code=code, name=name, description=description, is_active=True, metadata_json={})
    session.add(strategy)
    session.flush()
    session.commit()
    return strategy


def main() -> None:
    session = SessionLocal()
    try:
        # --- Bootstrapping refs
        bot_repo = BotRepository(session)
        runtime = BotRuntimeService(bot_repo)
        bot = runtime.register_bot_instance(
            instance_name="mi-ac-test",
            host_name=socket.gethostname(),
            process_id=99997,
            metadata={"scope": "market_intelligence_acceptance"},
        )
        runtime.mark_running(bot.id)

        market_repo = MarketRepository(session)
        regime_repo = RegimeRepository(session)
        strategy_repo = StrategyRepository(session)

        symbol = market_repo.get_or_create_symbol(name="XAUUSD_MI_TEST")
        timeframe = market_repo.get_or_create_timeframe(code="M5", minutes=5, description="M5")
        session.commit()

        # --- Create active strategy catalog used by selector
        ensure_strategy(session, "EMA_ATR_TREND", "EMA ATR Trend", "Trend following strategy")
        ensure_strategy(session, "VOLATILITY_BREAKOUT", "Volatility Breakout", "Breakout strategy")
        ensure_strategy(session, "RANGE_REVERSION", "Range Reversion", "Mean reversion strategy")

        # --- Build synthetic candle history with trend
        start = datetime.now(timezone.utc) - timedelta(minutes=5 * 120)
        rows: list[dict[str, Any]] = []
        price = 2300.0
        for i in range(120):
            open_price = price
            close_price = price + 0.15
            high_price = close_price + 0.05
            low_price = open_price - 0.05
            rows.append(
                {
                    "time": start + timedelta(minutes=5 * i),
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                }
            )
            price = close_price

        context = TradingContext.from_candle_event(
            {
                "symbol": "XAUUSD_MI_TEST",
                "timeframe": "M5",
                "candle_time": rows[-1]["time"].isoformat(),
                "open": rows[-1]["open"],
                "high": rows[-1]["high"],
                "low": rows[-1]["low"],
                "close": rows[-1]["close"],
                "tick_volume": 100,
            }
        )
        context.ingestion_result = {
            "symbol_id": symbol.id,
            "timeframe_ids": {"M5": timeframe.id},
            "rates_by_timeframe": {"M5": FakeFrame(rows)},
        }

        # [1] Regime tersimpan ke DB
        regime_engine = MarketRegimeEngine(regime_repository=regime_repo)
        context = regime_engine.run(context)
        regime_rows = session.execute(select(MarketRegime).where(MarketRegime.symbol_id == symbol.id, MarketRegime.timeframe_id == timeframe.id)).scalars().all()
        regime_saved = len(regime_rows) >= 1

        # [2] Selector pilih berdasar regime
        selector = StrategySelector(strategy_repository=strategy_repo)
        selector_context = TradingContext.from_candle_event(
            {
                "symbol": "XAUUSD_MI_TEST",
                "timeframe": "M5",
                "candle_time": datetime.now(timezone.utc).isoformat(),
                "open": 2300,
                "high": 2304,
                "low": 2299,
                "close": 2303,
                "tick_volume": 10,
            }
        )
        selector_context.ingestion_result = {"symbol_id": symbol.id, "timeframe_ids": {"M5": timeframe.id}}
        selector_context.regime_result = RegimeResult(
            regime=MarketRegimeType.TRENDING_BULLISH,
            confidence=0.8,
            is_tradeable=True,
            features={"atr": 2.0, "trend_strength": 1.1},
        )
        selector_context = selector.run(selector_context)
        selected_code = selector_context.strategy_selection.strategy_code.upper() if selector_context.strategy_selection else ""
        selector_ok = (not selector_context.rejected) and ("TREND" in selected_code)

        # [3] CHOPPY no trade
        choppy_context = TradingContext.from_candle_event(
            {
                "symbol": "XAUUSD_MI_TEST",
                "timeframe": "M5",
                "candle_time": datetime.now(timezone.utc).isoformat(),
                "open": 1,
                "high": 2,
                "low": 0.5,
                "close": 1.5,
                "tick_volume": 1,
            }
        )
        choppy_context.ingestion_result = {"symbol_id": symbol.id, "timeframe_ids": {"M5": timeframe.id}}
        choppy_context.regime_result = RegimeResult(
            regime=MarketRegimeType.CHOPPY,
            confidence=0.9,
            is_tradeable=False,
            reason="choppy test",
            features={},
        )
        choppy_context = selector.run(choppy_context)
        choppy_no_trade = choppy_context.rejected and choppy_context.rejection_reason == "NO_STRATEGY_SELECTED"

        # [4] Strategy engine menghasilkan RawSignal atau no signal
        strategy_engine = StrategyEngine(reject_on_no_signal=True)
        signal_context = TradingContext.from_candle_event(
            {
                "symbol": "XAUUSD_MI_TEST",
                "timeframe": "M5",
                "candle_time": datetime.now(timezone.utc).isoformat(),
                "open": 2300,
                "high": 2304,
                "low": 2299,
                "close": 2303,
                "tick_volume": 10,
            }
        )
        signal_context.market_snapshot = MarketSnapshot(
            symbol="XAUUSD_MI_TEST",
            timeframe="M5",
            candle_time=datetime.now(timezone.utc),
            open_price=2300,
            high_price=2304,
            low_price=2299,
            close_price=2303,
            tick_volume=10,
            spread=2,
        )
        signal_context.regime_result = RegimeResult(
            regime=MarketRegimeType.TRENDING_BULLISH,
            confidence=0.8,
            is_tradeable=True,
            features={"atr": 2.0, "trend_strength": 1.2},
        )
        signal_context.strategy_selection = StrategySelectionResult(
            strategy_code="EMA_ATR_TREND",
            strategy_name="EMA ATR Trend",
            score=0.8,
            config={},
            details={},
        )
        signal_context = strategy_engine.run(signal_context)
        strategy_signal_ok = (signal_context.raw_signal is not None) or (
            signal_context.rejected and signal_context.rejection_reason == "NO_SIGNAL_GENERATED"
        )

        print("regime_saved_to_db", regime_saved)
        print("selector_choose_by_regime", selector_ok)
        print("choppy_no_trade", choppy_no_trade)
        print("strategy_engine_signal_or_no_signal", strategy_signal_ok)
    finally:
        session.close()


if __name__ == "__main__":
    main()
