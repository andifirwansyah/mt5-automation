"""Historical edge validation result model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class EdgeResult:
    """Output contract for historical edge checks."""

    passed: bool
    sample_size: int
    win_rate: float
    expectancy: float
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
