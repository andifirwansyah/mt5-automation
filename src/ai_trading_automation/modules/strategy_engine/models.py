"""Models for strategy engine outputs."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class RawSignalCandidate:
    """Raw signal output produced by strategy engine shell."""

    symbol: str
    timeframe: str
    strategy_key: str
    direction: str
    confidence: float
    reason: str
    created_at: datetime
    metadata: dict[str, str | float | int | bool] = field(default_factory=dict)
