"""Contracts for trade journal module."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ai_trading_automation.modules.execution_gate.models import ExecutionDecision
from ai_trading_automation.modules.paper_execution.models import PaperOrder
from ai_trading_automation.modules.position_monitor.models import PositionState
from ai_trading_automation.modules.pre_trade_simulation.models import SimulationResult
from ai_trading_automation.modules.risk_engine.models import RiskPlan
from ai_trading_automation.modules.signal_validator.models import SignalValidationResult


@dataclass(slots=True)
class JournalWriteRequest:
    """Input payload for writing one journal entry."""

    signal_validation: SignalValidationResult
    risk_plan: RiskPlan
    simulation_result: SimulationResult
    execution_decision: ExecutionDecision
    order_state: PaperOrder | None = None
    result: PositionState | None = None
    notes: list[str] = field(default_factory=list)
    closed_at: datetime | None = None


@dataclass(slots=True)
class JournalReadRequest:
    """Input payload for reading journal entries."""

    journal_path: Path
    limit: int | None = None
