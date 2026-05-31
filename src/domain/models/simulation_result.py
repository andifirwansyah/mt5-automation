"""Pre-trade simulation result model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SimulationResult:
    """Output contract for pre-trade simulation checks."""

    passed: bool
    expected_profit: float
    expected_drawdown: float
    slippage_estimate: float
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
