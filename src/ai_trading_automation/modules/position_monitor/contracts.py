"""Contracts for position monitor module."""

from dataclasses import dataclass
from datetime import datetime

from ai_trading_automation.modules.paper_execution.models import PaperOrder


@dataclass(slots=True)
class MarketCandle:
    """Minimal candle contract for position monitoring."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(slots=True)
class PositionMonitorRequest:
    """Input contract for updating paper position state."""

    order: PaperOrder
    candle: MarketCandle
    both_hit_rule: str = "CONSERVATIVE_SL_FIRST"
