"""Broker health check result model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BrokerHealth:
    """Output contract for broker/MT5 health checks."""

    is_healthy: bool
    is_connected: bool
    is_trade_allowed: bool
    spread: float | None = None
    latency_ms: int | None = None
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
