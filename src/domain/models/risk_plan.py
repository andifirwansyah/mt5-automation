"""Risk planning domain model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RiskPlan:
    """Output contract from Risk Engine."""

    passed: bool
    lot_size: float
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_per_trade_pct: float
    max_daily_loss_pct: float
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
