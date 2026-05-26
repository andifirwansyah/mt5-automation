"""Models for trade journal entries."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class TradeJournalEntry:
    """Stored trade journal entry for one pipeline decision."""

    journal_id: str
    signal: dict[str, Any] | None
    signal_validation: dict[str, Any]
    risk_plan: dict[str, Any]
    simulation_result: dict[str, Any]
    execution_decision: dict[str, Any]
    order_state: dict[str, Any] | None
    result: dict[str, Any] | None
    notes: list[str]
    created_at: datetime
    closed_at: datetime | None
