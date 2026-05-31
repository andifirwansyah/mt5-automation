"""Position state domain model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class PositionState:
    """Unified internal representation of a trading position."""

    symbol: str
    side: str
    volume_lot: float
    entry_price: float
    stop_loss: float
    take_profit: float
    status: str
    opened_at: datetime
    current_price: float | None = None
    profit: float | None = None
    closed_at: datetime | None = None
    details: dict[str, Any] = field(default_factory=dict)
