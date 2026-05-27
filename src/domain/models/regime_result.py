"""Market regime detection result model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.domain.enums import MarketRegimeType


@dataclass(slots=True)
class RegimeResult:
    """Output contract of Market Regime Engine."""

    regime: MarketRegimeType
    confidence: float
    is_tradeable: bool
    reason: str | None = None
    features: dict[str, Any] = field(default_factory=dict)
