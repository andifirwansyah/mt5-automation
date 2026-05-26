"""Models for core pipeline orchestrator output."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class PipelineRunResult:
    """End-to-end pipeline run summary."""

    success: bool
    stage: str
    message: str
    decision: str | None
    run_at: datetime
    artifacts: dict[str, Any] = field(default_factory=dict)
