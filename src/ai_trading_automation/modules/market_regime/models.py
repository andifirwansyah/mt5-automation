"""Models for market regime detection output."""

from dataclasses import dataclass


@dataclass(slots=True)
class MarketRegimeResult:
    """Market regime analysis result for one symbol/timeframe."""

    symbol: str
    timeframe: str
    regime: str
    confidence: float
    volatility_state: str
    trend_strength: float
    range_state: str
    notes: list[str]
