"""Service for order/position lifecycle synchronization and journal updates."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.infrastructure.mt5.mt5_positions import MT5PositionClient
from src.repositories.journal_repository import JournalRepository
from src.repositories.position_repository import PositionRepository


class TradeLifecycleService:
    """Detect closed positions and append journal updates."""

    def __init__(
        self,
        position_client: MT5PositionClient,
        position_repository: PositionRepository,
        journal_repository: JournalRepository,
    ) -> None:
        self.position_client = position_client
        self.position_repository = position_repository
        self.journal_repository = journal_repository

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    def detect_order_position_lifecycle(self, account_id: uuid.UUID) -> dict[str, int | list]:
        mt5_open_positions = self.position_client.get_open_positions()
        mt5_open_tickets = {int(p.get("ticket", 0)) for p in mt5_open_positions}

        db_open_positions = self.position_repository.get_open_positions(account_id=account_id)

        closed_count = 0
        closed_positions = []
        for db_pos in db_open_positions:
            ticket = db_pos.mt5_position_ticket
            if ticket is None:
                continue
            if int(ticket) in mt5_open_tickets:
                continue

            details = db_pos.details or {}
            close_price = float(details.get("price_current") or db_pos.close_price or db_pos.entry_price)
            profit = float(details.get("profit") or db_pos.profit or 0.0)

            closed = self.position_repository.close_position(
                position_id=db_pos.id,
                close_price=close_price,
                profit=profit,
                closed_at=self._utc_now(),
            )
            if closed is None:
                continue

            self.journal_repository.create_trade_journal(
                journal_type="POSITION_CLOSED",
                message=f"Position closed for ticket={ticket}",
                position_id=closed.id,
                details={"ticket": int(ticket), "source": "trade_lifecycle_service"},
            )
            closed_count += 1
            closed_positions.append(closed)

        self.position_repository.session.commit()
        return {
            "open_positions_mt5": len(mt5_open_positions),
            "closed_positions_db": closed_count,
            "closed_positions": closed_positions,
        }
