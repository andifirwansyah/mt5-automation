"""Execution gate decision model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.domain.enums import ExecutionDecisionStatus


@dataclass(slots=True)
class ExecutionDecision:
    """Output contract for execution gate and approval stub."""

    status: ExecutionDecisionStatus
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def approved(self) -> bool:
        return self.status == ExecutionDecisionStatus.APPROVED
