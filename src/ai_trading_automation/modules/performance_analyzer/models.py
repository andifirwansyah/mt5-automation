"""Models for performance analyzer report."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class PerformanceReport:
    """Aggregated performance metrics from trade journal entries."""

    total_entries: int
    total_trades: int
    closed_trades: int
    wins: int
    losses: int
    win_rate: float
    avg_r: float
    max_drawdown: float
    rejection_count: int
    rejection_rate: float
    notes: list[str] = field(default_factory=list)
    generated_at: datetime | None = None
