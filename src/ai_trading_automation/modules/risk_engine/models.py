"""Models for risk engine output."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class RiskPlan:
    """Risk calculation output used by execution decision layer."""

    risk_amount: float
    risk_percent: float
    lot_size: float
    stop_loss: float
    risk_reward_ratio: float
    max_loss: float
    notes: list[str] = field(default_factory=list)
