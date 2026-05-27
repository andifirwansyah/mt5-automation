"""Execution result model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.domain.enums import OrderExecutionStatus


@dataclass(slots=True)
class OrderResult:
    """Result of execution engine operation."""

    status: OrderExecutionStatus
    dry_run: bool
    submitted_at: datetime | None = None
    order_ticket: int | None = None
    error_message: str | None = None
    request_payload: dict[str, Any] = field(default_factory=dict)
    response_payload: dict[str, Any] = field(default_factory=dict)
