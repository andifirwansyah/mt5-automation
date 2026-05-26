"""Contracts for paper execution module."""

from dataclasses import dataclass

from ai_trading_automation.modules.execution_gate.models import ExecutionDecision


@dataclass(slots=True)
class CreatePaperOrderRequest:
    """Input contract for creating a paper order."""

    execution_decision: ExecutionDecision
