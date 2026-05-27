"""Signal validation result model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.domain.enums import ValidationStatus


@dataclass(slots=True)
class ValidationResult:
    """Output contract for signal-level validators."""

    status: ValidationStatus
    reason: str | None = None
    validator_name: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == ValidationStatus.PASSED
