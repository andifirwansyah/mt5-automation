"""Models for position monitor output."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class PositionState:
    """Current position state after processing one candle."""

    order_id: str
    status: str
    direction: str
    entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float | None
    exit_reason: str | None
    hit_stop_loss: bool
    hit_take_profit: bool
    updated_at: datetime
