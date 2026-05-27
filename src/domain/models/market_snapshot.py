"""Market snapshot domain model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class MarketSnapshot:
    """Normalized candle/tick snapshot used by the pipeline."""

    symbol: str
    timeframe: str
    candle_time: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    tick_volume: int
    spread: int | None = None
    bid: float | None = None
    ask: float | None = None
    features: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)
