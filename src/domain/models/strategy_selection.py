"""Strategy selection result model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class StrategySelectionResult:
    """Output contract of Strategy Selector engine."""

    strategy_code: str
    strategy_name: str
    score: float
    reason: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
