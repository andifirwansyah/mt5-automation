"""Contracts for execution gate module."""

from dataclasses import dataclass, field

from ai_trading_automation.modules.pre_trade_simulation.models import SimulationResult
from ai_trading_automation.modules.risk_engine.models import RiskPlan
from ai_trading_automation.modules.signal_validator.models import SignalValidationResult


@dataclass(slots=True)
class ExecutionGateThresholds:
    """Thresholds to keep gate behavior explicit and conservative."""

    min_signal_score: float = 60.0
    reduce_risk_percent_threshold: float = 0.90
    min_risk_reward_ratio: float = 1.20


@dataclass(slots=True)
class ExecutionGateRequest:
    """Input contract for execution gate decisioning."""

    signal_validation: SignalValidationResult
    risk_plan: RiskPlan
    simulation_result: SimulationResult
    thresholds: ExecutionGateThresholds = field(default_factory=ExecutionGateThresholds)
