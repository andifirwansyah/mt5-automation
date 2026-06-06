"""Signal quality score contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class SignalQualityResult:
    """Composite score for signal quality before validation/risk stages."""

    passed: bool
    score: float
    grade: str
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    scored_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
