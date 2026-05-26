"""Models for strategy selector results."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class SelectedStrategy:
    """Selected strategy decision based on market regime."""

    symbol: str
    timeframe: str
    regime: str
    strategy_key: str
    decision: str
    confidence: float
    reason: str
    candidate_strategies: list[str] = field(default_factory=list)
