"""Models for execution gate decisions."""

from dataclasses import dataclass
from datetime import datetime

from ai_trading_automation.modules.risk_engine.models import RiskPlan
from ai_trading_automation.modules.signal_contract.models import SignalContract


@dataclass(slots=True)
class ExecutionDecision:
    """Final decision before paper execution stage."""

    decision: str
    reason: str
    risk_plan: RiskPlan
    signal: SignalContract | None
    created_at: datetime
