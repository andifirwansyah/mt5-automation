"""Service layer for normalizing raw strategy output into signal contract."""

from uuid import uuid4

from pydantic import ValidationError

from .contracts import SignalContractBuildRequest
from .errors import SignalContractBuildError
from .models import SignalContract, SignalDirection


class SignalContractService:
    """Build stable signal contract from strategy engine raw candidate."""

    def build(self, request: SignalContractBuildRequest) -> SignalContract:
        """Convert raw candidate into validated signal contract."""
        raw = request.raw_candidate
        if raw is None:
            raise SignalContractBuildError("raw_candidate must be provided.")

        direction = self._normalize_direction(raw.direction)
        metadata = dict(raw.metadata)
        entry_price, stop_loss, take_profit = self._resolve_price_fields(direction=direction, metadata=metadata)

        payload = {
            "signal_id": str(uuid4()),
            "symbol": raw.symbol,
            "timeframe": raw.timeframe,
            "direction": direction,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "strategy_key": raw.strategy_key,
            "confidence": raw.confidence,
            "reason": raw.reason,
            "created_at": raw.created_at,
            "metadata": metadata,
        }

        try:
            return SignalContract.model_validate(payload)
        except ValidationError as error:
            raise SignalContractBuildError(f"Failed to build signal contract: {error}") from error

    def _normalize_direction(self, direction: str) -> SignalDirection:
        try:
            return SignalDirection(direction.upper())
        except ValueError as error:
            raise SignalContractBuildError(f"Invalid direction from raw candidate: {direction}") from error

    def _resolve_price_fields(
        self,
        direction: SignalDirection,
        metadata: dict[str, str | float | int | bool],
    ) -> tuple[float | None, float | None, float | None]:
        if direction == SignalDirection.WAIT:
            return None, None, None

        required_fields = ("entry_price", "stop_loss", "take_profit")
        missing = [field for field in required_fields if field not in metadata]
        if missing:
            raise SignalContractBuildError(
                f"Missing required price fields in metadata for {direction}: {missing}"
            )

        try:
            entry_price = float(metadata["entry_price"])
            stop_loss = float(metadata["stop_loss"])
            take_profit = float(metadata["take_profit"])
        except (TypeError, ValueError) as error:
            raise SignalContractBuildError("Price metadata values must be numeric.") from error

        return entry_price, stop_loss, take_profit
