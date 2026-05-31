from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from src.infrastructure.database.session import SessionLocal


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def unique_suffix() -> str:
    return uuid.uuid4().hex[:10]


def build_candle_event(symbol: str = "XAUUSD", timeframe: str = "M5") -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "candle_time": now.isoformat(),
        "open": 2300.0,
        "high": 2302.0,
        "low": 2299.0,
        "close": 2301.0,
        "tick_volume": 100,
        "spread": 10,
    }


def build_rates_dataframe(count: int = 80, start_price: float = 2200.0) -> pd.DataFrame:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows: list[dict] = []
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
    return pd.DataFrame(rows)
