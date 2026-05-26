"""Models for paper execution module."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class PaperOrder:
    """Simulated order created from approved execution decision."""

    order_id: str
    signal_id: str
    symbol: str
    timeframe: str
    direction: str
    entry_price: float | None
    stop_loss: float | None
    take_profit: float | None
    lot_size: float
    status: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
