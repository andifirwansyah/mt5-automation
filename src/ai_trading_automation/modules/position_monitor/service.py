"""Service layer for paper position monitoring."""

from .contracts import PositionMonitorRequest
from .errors import PositionMonitorInputError
from .models import PositionState


class PositionMonitorService:
    """Update paper order position state from new candle."""

    def update(self, request: PositionMonitorRequest) -> PositionState:
        """Detect SL/TP hit and return updated position state."""
        self._validate_request(request)

        order = request.order
        candle = request.candle

        if order.status != "OPEN":
            return PositionState(
                order_id=order.order_id,
                status=order.status,
                direction=order.direction,
                entry_price=float(order.entry_price or 0.0),
                current_price=float(candle.close),
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                exit_reason="ORDER_ALREADY_CLOSED",
                hit_stop_loss=False,
                hit_take_profit=False,
                updated_at=candle.timestamp,
            )

        direction = order.direction
        entry_price = float(order.entry_price)
        stop_loss = float(order.stop_loss)
        take_profit = float(order.take_profit)
        lot_size = float(order.lot_size)

        if direction == "BUY":
            stop_hit = candle.low <= stop_loss
            take_hit = candle.high >= take_profit
        elif direction == "SELL":
            stop_hit = candle.high >= stop_loss
            take_hit = candle.low <= take_profit
        else:
            raise PositionMonitorInputError(f"Unsupported order direction: {direction}")

        if stop_hit and take_hit:
            if request.both_hit_rule == "CONSERVATIVE_SL_FIRST":
                exit_price = stop_loss
                exit_reason = "BOTH_HIT_ASSUME_SL"
            else:
                exit_price = take_profit
                exit_reason = "BOTH_HIT_ASSUME_TP"
            realized_pnl = self._calculate_pnl(direction, entry_price, exit_price, lot_size)
            return PositionState(
                order_id=order.order_id,
                status="CLOSED",
                direction=direction,
                entry_price=entry_price,
                current_price=exit_price,
                unrealized_pnl=0.0,
                realized_pnl=round(realized_pnl, 6),
                exit_reason=exit_reason,
                hit_stop_loss=True,
                hit_take_profit=True,
                updated_at=candle.timestamp,
            )

        if stop_hit:
            realized_pnl = self._calculate_pnl(direction, entry_price, stop_loss, lot_size)
            return PositionState(
                order_id=order.order_id,
                status="CLOSED",
                direction=direction,
                entry_price=entry_price,
                current_price=stop_loss,
                unrealized_pnl=0.0,
                realized_pnl=round(realized_pnl, 6),
                exit_reason="STOP_LOSS_HIT",
                hit_stop_loss=True,
                hit_take_profit=False,
                updated_at=candle.timestamp,
            )

        if take_hit:
            realized_pnl = self._calculate_pnl(direction, entry_price, take_profit, lot_size)
            return PositionState(
                order_id=order.order_id,
                status="CLOSED",
                direction=direction,
                entry_price=entry_price,
                current_price=take_profit,
                unrealized_pnl=0.0,
                realized_pnl=round(realized_pnl, 6),
                exit_reason="TAKE_PROFIT_HIT",
                hit_stop_loss=False,
                hit_take_profit=True,
                updated_at=candle.timestamp,
            )

        unrealized = self._calculate_pnl(direction, entry_price, float(candle.close), lot_size)
        return PositionState(
            order_id=order.order_id,
            status="OPEN",
            direction=direction,
            entry_price=entry_price,
            current_price=float(candle.close),
            unrealized_pnl=round(unrealized, 6),
            realized_pnl=None,
            exit_reason=None,
            hit_stop_loss=False,
            hit_take_profit=False,
            updated_at=candle.timestamp,
        )

    def _calculate_pnl(
        self,
        direction: str,
        entry_price: float,
        current_price: float,
        lot_size: float,
    ) -> float:
        if direction == "BUY":
            return (current_price - entry_price) * lot_size
        return (entry_price - current_price) * lot_size

    def _validate_request(self, request: PositionMonitorRequest) -> None:
        if request.order is None:
            raise PositionMonitorInputError("order must be provided.")
        if request.candle is None:
            raise PositionMonitorInputError("candle must be provided.")

        order = request.order
        if order.entry_price is None or order.stop_loss is None or order.take_profit is None:
            raise PositionMonitorInputError("Paper order must include entry_price, stop_loss, take_profit.")
