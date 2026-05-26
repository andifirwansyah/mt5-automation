"""Models for signal validator output."""

from dataclasses import dataclass

from ai_trading_automation.modules.signal_contract.models import SignalContract


@dataclass(slots=True)
class SignalValidationResult:
    """Validation result consumed by risk engine layer."""

    is_valid: bool
    score: float
    errors: list[str]
    warnings: list[str]
    rejection_reason: str | None
    validated_signal: SignalContract | None
