"""Repository for position lifecycle tables."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from src.infrastructure.database.models import ExecutionOrder, Position, PositionSnapshot


class PositionRepository:
    """CRUD/query repository for positions and snapshots."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_position(
        self,
        account_id: uuid.UUID,
        symbol_id: uuid.UUID,
        side: str,
        volume_lot: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        status: str,
        opened_at: datetime,
        execution_order_id: uuid.UUID | None = None,
        mt5_position_ticket: int | None = None,
        close_price: float | None = None,
        profit: float | None = None,
        closed_at: datetime | None = None,
        details: dict[str, Any] | None = None,
    ) -> Position:
        entity: Position | None = None
        if mt5_position_ticket is not None:
            stmt = select(Position).where(Position.mt5_position_ticket == mt5_position_ticket).limit(1)
            entity = self.session.execute(stmt).scalar_one_or_none()

        if entity is None:
            entity = Position(
                execution_order_id=execution_order_id,
                account_id=account_id,
                symbol_id=symbol_id,
                mt5_position_ticket=mt5_position_ticket,
                side=side,
                volume_lot=volume_lot,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                close_price=close_price,
                profit=profit,
                status=status,
                opened_at=opened_at,
                closed_at=closed_at,
                details=details or {},
            )
        else:
            entity.execution_order_id = execution_order_id or entity.execution_order_id
            entity.volume_lot = volume_lot
            entity.entry_price = entry_price
            entity.stop_loss = stop_loss
            entity.take_profit = take_profit
            entity.close_price = close_price
            entity.profit = profit
            entity.status = status
            entity.closed_at = closed_at
            entity.details = details or entity.details

        self.session.add(entity)
        self.session.flush()
        return entity

    def create_position_snapshot(
        self,
        position_id: uuid.UUID,
        snapshot_time: datetime,
        current_price: float,
        unrealized_profit: float,
        swap: float,
        commission: float,
        raw_payload: dict[str, Any] | None = None,
    ) -> PositionSnapshot:
        entity = PositionSnapshot(
            position_id=position_id,
            snapshot_time=snapshot_time,
            current_price=current_price,
            unrealized_profit=unrealized_profit,
            swap=swap,
            commission=commission,
            raw_payload=raw_payload or {},
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def get_open_positions(self, account_id: uuid.UUID | None = None, symbol_id: uuid.UUID | None = None) -> list[Position]:
        stmt = select(Position).where(Position.status == "OPEN")
        if account_id is not None:
            stmt = stmt.where(Position.account_id == account_id)
        if symbol_id is not None:
            stmt = stmt.where(Position.symbol_id == symbol_id)
        stmt = stmt.order_by(Position.opened_at.desc())
        return list(self.session.execute(stmt).scalars().all())

    def close_position(
        self,
        position_id: uuid.UUID,
        close_price: float,
        profit: float,
        closed_at: datetime,
        status: str = "CLOSED",
    ) -> Position | None:
        entity = self.session.get(Position, position_id)
        if entity is None:
            return None

        details = entity.details or {}
        detail_close_price = float(details.get("price_current") or 0.0)
        detail_profit = float(details.get("profit") or 0.0)
        entry_price = float(entity.entry_price)

        resolved_close_price = close_price
        if detail_profit != 0.0 and (resolved_close_price <= 0 or resolved_close_price == entry_price) and detail_close_price > 0:
            resolved_close_price = detail_close_price or close_price

        resolved_profit = profit
        if resolved_profit == 0.0 and detail_profit != 0.0:
            resolved_profit = detail_profit

        entity.close_price = resolved_close_price
        entity.profit = resolved_profit
        entity.closed_at = closed_at
        entity.status = status
        self.session.add(entity)
        self.session.flush()
        return entity

    def find_matching_execution_order_id(
        self,
        symbol_id: uuid.UUID,
        side: str,
        volume_lot: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        opened_at: datetime,
    ) -> uuid.UUID | None:
        candidate_time_lower = opened_at.replace(hour=0, minute=0, second=0, microsecond=0)
        candidate_time_upper = opened_at

        stmt = (
            select(ExecutionOrder)
            .outerjoin(Position, Position.execution_order_id == ExecutionOrder.id)
            .where(
                ExecutionOrder.symbol_id == symbol_id,
                ExecutionOrder.side == side,
                ExecutionOrder.status.in_(["FILLED", "SUBMITTED"]),
                Position.id.is_(None),
                or_(
                    ExecutionOrder.executed_at.is_(None),
                    and_(
                        ExecutionOrder.executed_at >= candidate_time_lower,
                        ExecutionOrder.executed_at <= candidate_time_upper,
                    ),
                ),
            )
            .order_by(ExecutionOrder.executed_at.desc().nullslast(), ExecutionOrder.created_at.desc())
            .limit(25)
        )
        candidates = list(self.session.execute(stmt).scalars().all())
        if not candidates:
            return None

        def _score(order: ExecutionOrder) -> tuple[float, float]:
            price_score = abs(float(order.requested_price) - entry_price)
            sl_score = abs(float(order.stop_loss) - stop_loss)
            tp_score = abs(float(order.take_profit) - take_profit)
            volume_score = abs(float(order.volume_lot) - volume_lot)
            order_time = order.executed_at or order.created_at or opened_at
            time_score = abs((opened_at - order_time).total_seconds())
            return (volume_score + price_score + sl_score + tp_score, time_score)

        best = min(candidates, key=_score)
        best_volume_diff = abs(float(best.volume_lot) - volume_lot)
        if best_volume_diff > 0.0001:
            return None
        return best.id
