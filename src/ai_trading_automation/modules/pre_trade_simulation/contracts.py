"""Contracts for pre-trade simulation module."""

from dataclasses import dataclass, field

from ai_trading_automation.modules.risk_engine.models import RiskPlan
from ai_trading_automation.modules.signal_validator.models import SignalValidationResult


@dataclass(slots=True)
class SimulationAssumptions:
    """Deterministic assumptions for spread/slippage/adverse movement."""

    spread_percent: float = 0.0004
    slippage_percent: float = 0.0004
    adverse_move_factor: float = 0.20
    max_worst_case_loss_factor: float = 1.35
    spread_extreme_threshold: float = 0.0025
    slippage_extreme_threshold: float = 0.0030


@dataclass(slots=True)
class PreTradeSimulationRequest:
    """Input contract for pre-trade simulation."""

    signal_validation: SignalValidationResult
    risk_plan: RiskPlan
    assumptions: SimulationAssumptions = field(default_factory=SimulationAssumptions)
