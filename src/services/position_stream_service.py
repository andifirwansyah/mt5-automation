"""Services for realtime position WebSocket streaming from DB-backed state."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.deps import serialize_value
from src.infrastructure.database.models import Position, PositionSnapshot, Symbol


@dataclass(frozen=True)
class PositionStreamItem:
    event: str
    position: dict[str, Any]


class PositionStreamService:
    """Load and diff current position state for realtime streaming."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def load_open_positions(self) -> dict[str, dict[str, Any]]:
        stmt = (
            select(Position, Symbol.name)
            .join(Symbol, Symbol.id == Position.symbol_id)
            .where(Position.status == "OPEN")
            .order_by(Position.opened_at.desc())
        )
        rows = self.session.execute(stmt).all()

        items: dict[str, dict[str, Any]] = {}
        for position, symbol_name in rows:
            items[str(position.id)] = self._build_position_payload(position=position, symbol_name=str(symbol_name))
        return items

    def get_positions_by_ids(self, position_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not position_ids:
            return {}

        parsed_ids = [uuid.UUID(value) for value in position_ids]
        stmt = (
            select(Position, Symbol.name)
            .join(Symbol, Symbol.id == Position.symbol_id)
            .where(Position.id.in_(parsed_ids))
        )
        rows = self.session.execute(stmt).all()
        return {
            str(position.id): self._build_position_payload(position=position, symbol_name=str(symbol_name))
            for position, symbol_name in rows
        }

    def diff_positions(
        self,
        previous_state: dict[str, dict[str, Any]],
        current_state: dict[str, dict[str, Any]],
    ) -> list[PositionStreamItem]:
        events: list[PositionStreamItem] = []

        previous_ids = set(previous_state.keys())
        current_ids = set(current_state.keys())

        for position_id in sorted(current_ids - previous_ids):
            events.append(PositionStreamItem(event="position.opened", position=current_state[position_id]))

        for position_id in sorted(current_ids & previous_ids):
            if current_state[position_id] != previous_state[position_id]:
                events.append(PositionStreamItem(event="position.updated", position=current_state[position_id]))

        closed_items = self.get_positions_by_ids(sorted(previous_ids - current_ids))
        for position_id in sorted(previous_ids - current_ids):
            payload = closed_items.get(position_id)
            if payload is not None:
                events.append(PositionStreamItem(event="position.closed", position=payload))

        return events

    def _latest_snapshot(self, position_id: uuid.UUID) -> PositionSnapshot | None:
        stmt = (
            select(PositionSnapshot)
            .where(PositionSnapshot.position_id == position_id)
            .order_by(PositionSnapshot.snapshot_time.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def _build_position_payload(self, position: Position, symbol_name: str) -> dict[str, Any]:
        latest_snapshot = self._latest_snapshot(position.id)
        snapshot_payload = None
        if latest_snapshot is not None:
            snapshot_payload = {
                "snapshot_time": serialize_value(latest_snapshot.snapshot_time),
                "current_price": serialize_value(latest_snapshot.current_price),
                "unrealized_profit": serialize_value(latest_snapshot.unrealized_profit),
                "swap": serialize_value(latest_snapshot.swap),
                "commission": serialize_value(latest_snapshot.commission),
            }

        payload = {
            "id": serialize_value(position.id),
            "account_id": serialize_value(position.account_id),
            "symbol_id": serialize_value(position.symbol_id),
            "symbol": symbol_name,
            "execution_order_id": serialize_value(position.execution_order_id),
            "mt5_position_ticket": serialize_value(position.mt5_position_ticket),
            "side": serialize_value(position.side),
            "volume_lot": serialize_value(position.volume_lot),
            "entry_price": serialize_value(position.entry_price),
            "stop_loss": serialize_value(position.stop_loss),
            "take_profit": serialize_value(position.take_profit),
            "close_price": serialize_value(position.close_price),
            "profit": serialize_value(position.profit),
            "status": serialize_value(position.status),
            "opened_at": serialize_value(position.opened_at),
            "closed_at": serialize_value(position.closed_at),
            "created_at": serialize_value(position.created_at),
            "updated_at": serialize_value(position.updated_at),
            "details": serialize_value(position.details or {}),
            "latest_snapshot": snapshot_payload,
        }
        return payload
