"""Service layer for conservative risk plan calculation."""

from .contracts import RiskEngineRequest
from .errors import RiskEngineInputError, RiskLimitExceededError
from .models import RiskPlan


class RiskEngineService:
    """Calculate risk amount, conceptual lot size, and enforce guard rails."""

    def calculate(self, request: RiskEngineRequest) -> RiskPlan:
        """Calculate risk plan and reject requests violating risk policy limits."""
        self._validate_request(request)

        signal = request.signal
        if signal.direction not in {"BUY", "SELL"}:
            raise RiskEngineInputError("Risk plan can only be calculated for BUY/SELL signals.")

        entry_price = float(signal.entry_price)
        stop_loss = float(signal.stop_loss)
        take_profit = float(signal.take_profit)

        if signal.direction == "BUY" and stop_loss >= entry_price:
            raise RiskEngineInputError("Invalid BUY signal: stop_loss must be below entry_price.")
        if signal.direction == "SELL" and stop_loss <= entry_price:
            raise RiskEngineInputError("Invalid SELL signal: stop_loss must be above entry_price.")

        sl_distance = abs(entry_price - stop_loss)
        if sl_distance <= 0:
            raise RiskEngineInputError("Stop-loss distance must be greater than zero.")

        risk_percent = request.requested_risk_percent
        risk_amount = request.account_balance * (risk_percent / 100.0)

        daily_loss_limit_amount = request.account_balance * (request.config.max_daily_loss_percent / 100.0)
        projected_daily_loss = request.daily_realized_loss + risk_amount
        if projected_daily_loss > daily_loss_limit_amount:
            raise RiskLimitExceededError(
                "Projected daily loss exceeds max daily loss limit "
                f"({projected_daily_loss:.2f} > {daily_loss_limit_amount:.2f})."
            )

        lot_size = risk_amount / sl_distance
        if lot_size < 0:
            raise RiskEngineInputError("Calculated lot size cannot be negative.")

        reward_distance = abs(take_profit - entry_price)
        risk_reward_ratio = reward_distance / sl_distance if sl_distance > 0 else 0.0

        notes = [
            f"Risk policy: max_trade={request.config.max_risk_per_trade_percent:.2f}%.",
            f"Risk policy: max_daily_loss={request.config.max_daily_loss_percent:.2f}%.",
            f"Open positions: {request.open_positions_count}/{request.config.max_open_positions}.",
        ]

        return RiskPlan(
            risk_amount=round(risk_amount, 6),
            risk_percent=round(risk_percent, 6),
            lot_size=round(lot_size, 6),
            stop_loss=stop_loss,
            risk_reward_ratio=round(risk_reward_ratio, 6),
            max_loss=round(risk_amount, 6),
            notes=notes,
        )

    def _validate_request(self, request: RiskEngineRequest) -> None:
        if request.signal is None:
            raise RiskEngineInputError("signal must be provided.")
        if request.account_balance <= 0:
            raise RiskEngineInputError("account_balance must be greater than zero.")
        if request.daily_realized_loss < 0:
            raise RiskEngineInputError("daily_realized_loss cannot be negative.")
        if request.open_positions_count < 0:
            raise RiskEngineInputError("open_positions_count cannot be negative.")

        config = request.config
        if config.max_open_positions <= 0:
            raise RiskEngineInputError("max_open_positions must be greater than zero.")
        if request.open_positions_count >= config.max_open_positions:
            raise RiskLimitExceededError(
                f"Max open positions reached ({request.open_positions_count}/{config.max_open_positions})."
            )

        if request.requested_risk_percent <= 0:
            raise RiskEngineInputError("requested_risk_percent must be greater than zero.")
        if request.requested_risk_percent > config.max_risk_per_trade_percent:
            raise RiskLimitExceededError(
                "Requested risk percent exceeds max risk per trade "
                f"({request.requested_risk_percent:.2f}% > {config.max_risk_per_trade_percent:.2f}%)."
            )
