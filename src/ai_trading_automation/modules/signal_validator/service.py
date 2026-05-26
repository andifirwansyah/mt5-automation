"""Service layer for conservative signal validation."""

from .contracts import SignalValidationRequest
from .errors import SignalValidatorInputError
from .models import SignalValidationResult


class SignalValidatorService:
    """Validate standardized signal completeness, price relation, and regime conflict."""

    def validate(self, request: SignalValidationRequest) -> SignalValidationResult:
        """Return conservative validation result with score and rejection reason."""
        if request.signal is None:
            raise SignalValidatorInputError("signal must be provided.")

        signal = request.signal
        errors: list[str] = []
        warnings: list[str] = []

        score = max(0.0, min(100.0, signal.confidence * 100.0))
        if signal.direction == "WAIT":
            errors.append("WAIT direction is not tradable for risk engine stage.")

        if signal.direction == "BUY":
            if signal.stop_loss is None or signal.entry_price is None or signal.take_profit is None:
                errors.append("BUY signal must contain entry_price, stop_loss, take_profit.")
            else:
                if signal.stop_loss >= signal.entry_price:
                    errors.append("BUY signal invalid: stop_loss must be below entry_price.")
                if signal.take_profit <= signal.entry_price:
                    errors.append("BUY signal invalid: take_profit must be above entry_price.")

        if signal.direction == "SELL":
            if signal.stop_loss is None or signal.entry_price is None or signal.take_profit is None:
                errors.append("SELL signal must contain entry_price, stop_loss, take_profit.")
            else:
                if signal.stop_loss <= signal.entry_price:
                    errors.append("SELL signal invalid: stop_loss must be above entry_price.")
                if signal.take_profit >= signal.entry_price:
                    errors.append("SELL signal invalid: take_profit must be below entry_price.")

        regime = request.market_regime
        if regime is not None:
            if regime.regime == "TREND_UP" and signal.direction == "SELL":
                errors.append("Signal conflicts with TREND_UP regime (SELL not allowed).")
            elif regime.regime == "TREND_DOWN" and signal.direction == "BUY":
                errors.append("Signal conflicts with TREND_DOWN regime (BUY not allowed).")
            elif regime.regime in {"UNKNOWN", "CHOPPY"}:
                warnings.append(f"Regime {regime.regime} is low-quality for entry timing.")
            elif regime.regime == "LOW_VOLATILITY":
                warnings.append("LOW_VOLATILITY regime may reduce trade expectancy.")

        score -= len(errors) * 35.0
        score -= len(warnings) * 8.0
        score = max(0.0, min(100.0, score))

        rejection_reason: str | None = None
        is_valid = len(errors) == 0 and score >= request.min_score
        if not is_valid:
            if errors:
                rejection_reason = errors[0]
            elif score < request.min_score:
                rejection_reason = (
                    f"Signal score below minimum threshold: {score:.2f} < {request.min_score:.2f}"
                )

        return SignalValidationResult(
            is_valid=is_valid,
            score=round(score, 4),
            errors=errors,
            warnings=warnings,
            rejection_reason=rejection_reason,
            validated_signal=signal if is_valid else None,
        )
