"""Service layer for paper execution order simulation."""

from datetime import UTC, datetime
from uuid import uuid4

from ai_trading_automation.modules.position_monitor.models import PositionState

from .contracts import CreatePaperOrderRequest
from .errors import PaperExecutionBlockedError, PaperExecutionInputError
from .models import PaperOrder
from .repository import PaperOrderRepository


class PaperExecutionService:
    """Create and store paper orders from approved execution decisions."""

    def __init__(
        self,
        storage_backend: str = "memory",
        repository: PaperOrderRepository | None = None,
    ) -> None:
        self._orders: dict[str, PaperOrder] = {}
        self._storage_backend = storage_backend
        self._repository = repository

        if self._storage_backend == "db" and self._repository is None:
            raise PaperExecutionInputError("repository is required when storage_backend='db'.")

        if self._storage_backend not in {"memory", "db"}:
            raise PaperExecutionInputError("storage_backend must be either 'memory' or 'db'.")

    def create_order(self, request: CreatePaperOrderRequest) -> PaperOrder:
        """Create paper order only when execution gate decision is APPROVE."""
        if request.execution_decision is None:
            raise PaperExecutionInputError("execution_decision must be provided.")

        decision = request.execution_decision
        if decision.decision != "APPROVE":
            raise PaperExecutionBlockedError(
                f"Paper order creation blocked for decision '{decision.decision}'."
            )

        if decision.signal is None:
            raise PaperExecutionInputError("Approved decision must include signal payload.")

        signal = decision.signal
        now = datetime.now(tz=UTC)
        order = PaperOrder(
            order_id=str(uuid4()),
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            direction=signal.direction.value,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            lot_size=decision.risk_plan.lot_size,
            status="OPEN",
            created_at=now,
            updated_at=now,
            closed_at=None,
        )
        if self._storage_backend == "db":
            self._repository.save(order)
        else:
            self._orders[order.order_id] = order
        return order

    def get_order(self, order_id: str) -> PaperOrder | None:
        """Retrieve one order from in-memory state."""
        if self._storage_backend == "db":
            return self._repository.get_by_order_id(order_id)
        return self._orders.get(order_id)

    def sync_position_state(self, order_id: str, position_state: PositionState) -> None:
        """Synchronize order status from position monitor output."""
        if self._storage_backend == "db":
            self._repository.update_status(
                order_id=order_id,
                status=position_state.status,
                updated_at=position_state.updated_at,
                closed_at=position_state.updated_at if position_state.status == "CLOSED" else None,
            )
            return

        existing = self._orders.get(order_id)
        if existing is None:
            return
        existing.status = position_state.status
        existing.updated_at = position_state.updated_at
        existing.closed_at = position_state.updated_at if position_state.status == "CLOSED" else None
