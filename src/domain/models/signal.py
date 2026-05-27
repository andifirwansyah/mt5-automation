"""Signal models used between strategy and execution pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.domain.enums import SignalDirection


@dataclass(slots=True)
class RawSignal:
    """Raw strategy output prior to contract normalization."""

    direction: SignalDirection
    confidence: float
    entry_price: float
    stop_loss: float
    take_profit: float
    generated_at: datetime
    features: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SignalContract:
    """Normalized and executable signal contract."""

    symbol: str
    timeframe: str
    direction: SignalDirection
    entry_price: float
    stop_loss: float
    take_profit: float
    lot_size: float
    confidence: float
    generated_at: datetime
    strategy_code: str
    metadata: dict[str, Any] = field(default_factory=dict)
