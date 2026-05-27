"""Repository for kill switch and safety events."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.infrastructure.database.models import KillSwitchState, SafetyEvent


class SafetyRepository:
    """CRUD/query repository for safety tables."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    def get_active_kill_switch(self) -> KillSwitchState | None:
        stmt = (
            select(KillSwitchState)
            .where(KillSwitchState.is_active.is_(True), KillSwitchState.deactivated_at.is_(None))
            .order_by(KillSwitchState.created_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def activate_kill_switch(
        self,
        reason: str,
        activated_by: str | None = None,
        details: dict[str, Any] | None = None,
        activated_at: datetime | None = None,
    ) -> KillSwitchState:
        entity = KillSwitchState(
            is_active=True,
            reason=reason,
            activated_by=activated_by,
            activated_at=activated_at or self._utc_now(),
            details=details or {},
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def deactivate_kill_switch(
        self,
        deactivated_by: str | None = None,
        details: dict[str, Any] | None = None,
        deactivated_at: datetime | None = None,
    ) -> KillSwitchState | None:
        active = self.get_active_kill_switch()
        if active is None:
            return None

        active.is_active = False
        active.deactivated_by = deactivated_by
        active.deactivated_at = deactivated_at or self._utc_now()
        active.details = details or active.details
        self.session.add(active)
        self.session.flush()
        return active

    def create_safety_event(
        self,
        event_type: str,
        severity: str,
        status: str,
        message: str,
        related_trace_id: uuid.UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> SafetyEvent:
        entity = SafetyEvent(
            event_type=event_type,
            severity=severity,
            status=status,
            message=message,
            related_trace_id=related_trace_id,
            details=details or {},
        )
        self.session.add(entity)
        self.session.flush()
        return entity
