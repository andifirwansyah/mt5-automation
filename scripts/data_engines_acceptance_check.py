"""Acceptance checks for data engines using fake adapters."""

from __future__ import annotations

import sys
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.domain.models.market_snapshot import MarketSnapshot
from src.engines.data_collector_engine import DataCollectorEngine
from src.engines.data_quality_guard import DataQualityGuard
from src.engines.market_data_ingestion_engine import MarketDataIngestionEngine
from src.engines.mt5_listener_engine import MT5ListenerEngine
from src.infrastructure.database.session import SessionLocal
from src.pipeline.trading_context import TradingContext
from src.repositories.account_repository import AccountRepository
from src.repositories.market_repository import MarketRepository
from src.services.account_snapshot_service import AccountSnapshotService
from src.services.candle_service import CandleService


@dataclass
class _Row:
    data: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.data)


class _ILoc:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def __getitem__(self, item: int) -> _Row:
        return _Row(self._rows[item])


class SimpleDataFrame:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.iloc = _ILoc(self._rows)

    @property
    def empty(self) -> bool:
        return len(self._rows) == 0

    def __len__(self) -> int:
        return len(self._rows)

    def iterrows(self):
        for idx, row in enumerate(self._rows):
            yield idx, _Row(row)


class FakeListenerMarketData:
    def __init__(self, sequences: list[list[dict[str, Any]]]) -> None:
        self.sequences = sequences
        self._index = 0

    def get_rates(self, symbol: str, timeframe: str, count: int) -> list[dict[str, Any]]:
        if self._index >= len(self.sequences):
            return self.sequences[-1]
        value = self.sequences[self._index]
        self._index += 1
        return value

    def normalize_rates_to_dataframe(self, rates: Any) -> SimpleDataFrame:
        return SimpleDataFrame(deepcopy(rates or []))

    def get_tick(self, symbol: str) -> dict[str, Any]:
        return {"bid": 2300.0, "ask": 2300.2, "time": int(datetime.now(timezone.utc).timestamp())}


class FakeCollectorMarketData:
    def __init__(self, rates_by_tf: dict[str, list[dict[str, Any]]], tick: dict[str, Any]) -> None:
        self.rates_by_tf = rates_by_tf
        self.tick = tick

    def select_symbol(self, symbol: str) -> bool:
        return True

    def get_rates(self, symbol: str, timeframe: str, count: int) -> list[dict[str, Any]]:
        return deepcopy(self.rates_by_tf.get(timeframe, []))

    def normalize_rates_to_dataframe(self, rates: Any) -> SimpleDataFrame:
        return SimpleDataFrame(deepcopy(rates or []))

    def get_tick(self, symbol: str) -> dict[str, Any]:
        return dict(self.tick)


class FakeAccountClient:
    def get_account_info(self) -> dict[str, Any]:
        return {
            "login": 103266298,
            "name": "Demo Account",
            "server": "FBS-Demo",
            "currency": "USD",
            "leverage": 500,
            "balance": 10000.0,
            "equity": 10020.0,
            "margin": 20.0,
            "margin_free": 10000.0,
            "margin_level": 50100.0,
            "profit": 20.0,
        }


class FakePositionClient:
    def get_open_positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        return []


def main() -> None:
    # --- [1] Listener detect candle baru + [5] anti duplicate ---
    t1 = datetime.now(timezone.utc).replace(microsecond=0)
    t2 = t1 + timedelta(minutes=5)
    seq_same_1 = [{"time": t1, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "tick_volume": 10, "spread": 2}]
    seq_same_2 = [{"time": t1, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "tick_volume": 10, "spread": 2}]
    seq_new = [{"time": t2, "open": 1.6, "high": 2.1, "low": 1.2, "close": 1.9, "tick_volume": 12, "spread": 2}]

    listener_market = FakeListenerMarketData([seq_same_1, seq_same_2, seq_new])
    emitted: list[dict[str, Any]] = []
    listener = MT5ListenerEngine(
        market_data=listener_market,
        symbol="XAUUSD",
        timeframe="M5",
        on_new_candle=lambda event: emitted.append(event),
    )
    listener._poll_once()
    listener._poll_once()
    listener._poll_once()

    listener_detect_new = len(emitted) >= 2
    same_candle_not_twice = len(emitted) == 2

    # --- [2], [3], [4] collector + ingestion + quality guard ---
    session = SessionLocal()
    try:
        market_repo = MarketRepository(session)
        account_repo = AccountRepository(session)
        candle_service = CandleService(market_repo)
        account_snapshot_service = AccountSnapshotService(account_repo)

        collector_market = FakeCollectorMarketData(
            rates_by_tf={
                "M5": [
                    {"time": t1, "open": 2300.0, "high": 2302.0, "low": 2298.0, "close": 2301.0, "tick_volume": 100, "spread": 3},
                    {"time": t2, "open": 2301.0, "high": 2304.0, "low": 2300.0, "close": 2303.0, "tick_volume": 120, "spread": 3},
                ],
                "M15": [
                    {"time": t1, "open": 2299.0, "high": 2305.0, "low": 2297.0, "close": 2302.0, "tick_volume": 180, "spread": 4},
                ],
            },
            tick={"bid": 2303.0, "ask": 2303.2, "last": 2303.1, "time": int(t2.timestamp())},
        )

        collector = DataCollectorEngine(
            market_data=collector_market,
            account_client=FakeAccountClient(),
            position_client=FakePositionClient(),
            context_timeframes=["M15"],
            entry_candle_count=50,
            context_candle_count=50,
        )

        context = TradingContext.from_candle_event(
            {
                "symbol": "XAUUSD_AC_TEST",
                "timeframe": "M5",
                "candle_time": t2.isoformat(),
                "open": 2301.0,
                "high": 2304.0,
                "low": 2300.0,
                "close": 2303.0,
                "tick_volume": 120,
            }
        )
        context = collector.run(context)
        collector_snapshot_ok = context.market_snapshot is not None

        ingestion = MarketDataIngestionEngine(
            market_repository=market_repo,
            account_repository=account_repo,
            candle_service=candle_service,
            account_snapshot_service=account_snapshot_service,
        )
        context = ingestion.run(context)
        candles_saved_ok = int(context.ingestion_result.get("candles_saved", 0)) > 0

        guard = DataQualityGuard(market_repository=market_repo, candle_service=candle_service, max_spread=50.0)
        invalid_context = TradingContext.from_candle_event(
            {
                "symbol": "XAUUSD_AC_TEST",
                "timeframe": "M5",
                "candle_time": t2.isoformat(),
                "open": 10,
                "high": 5,
                "low": 7,
                "close": 9,
                "tick_volume": 1,
            }
        )
        invalid_context.market_snapshot = MarketSnapshot(
            symbol="XAUUSD_AC_TEST",
            timeframe="M5",
            candle_time=t2,
            open_price=10,
            high_price=5,
            low_price=7,
            close_price=9,
            tick_volume=1,
            spread=2,
        )
        invalid_context.ingestion_result = context.ingestion_result
        invalid_context = guard.run(invalid_context)
        data_quality_reject_ok = invalid_context.rejected and invalid_context.rejection_reason == "DATA_QUALITY_FAILED"
    finally:
        session.close()

    print("listener_detect_new", listener_detect_new)
    print("data_collector_market_snapshot", collector_snapshot_ok)
    print("candles_saved_postgresql", candles_saved_ok)
    print("data_quality_reject_invalid", data_quality_reject_ok)
    print("same_candle_not_processed_twice", same_candle_not_twice)


if __name__ == "__main__":
    main()
