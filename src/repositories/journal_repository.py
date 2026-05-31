"""Repository for trade journal table."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from src.infrastructure.database.models import TradeJournal


class JournalRepository:
    """CRUD/query repository for trade journal entries."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_trade_journal(
        self,
        journal_type: str,
        message: str,
        signal_id: uuid.UUID | None = None,
        order_id: uuid.UUID | None = None,
        position_id: uuid.UUID | None = None,
        trace_id: uuid.UUID | None = None,
        details: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TradeJournal:
        entity = TradeJournal(
            signal_id=signal_id,
            order_id=order_id,
            position_id=position_id,
            trace_id=trace_id,
            journal_type=journal_type,
            message=message,
            details=details or {},
            metadata_json=metadata or {},
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def update_trade_journal(
        self,
        journal_id: uuid.UUID,
        message: str | None = None,
        details: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TradeJournal | None:
        entity = self.session.get(TradeJournal, journal_id)
        if entity is None:
            return None

        if message is not None:
            entity.message = message
        if details is not None:
            entity.details = details
        if metadata is not None:
            entity.metadata_json = metadata
        self.session.add(entity)
        self.session.flush()
        return entity
