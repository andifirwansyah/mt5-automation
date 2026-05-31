"""Repository for bot runtime and engine audit tables."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from datetime import timedelta

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from src.infrastructure.database.models import BotInstance, BotRuntimeState, EngineRun


class BotRepository:
    """CRUD/query repository for bot state tables."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    def create_bot_instance(
        self,
        instance_name: str,
        host_name: str,
        process_id: int,
        status: str = "starting",
        metadata: dict[str, Any] | None = None,
        started_at: datetime | None = None,
    ) -> BotInstance:
        entity = BotInstance(
            instance_name=instance_name,
            host_name=host_name,
            process_id=process_id,
            status=status,
            metadata_json=metadata or {},
            started_at=started_at or self._utc_now(),
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def update_heartbeat(
        self,
        bot_instance_id: uuid.UUID,
        details: dict[str, Any] | None = None,
        trace_id: uuid.UUID | None = None,
    ) -> BotRuntimeState:
        state = self.get_runtime_state(bot_instance_id)
        if state is None:
            return self.upsert_runtime_state(
                bot_instance_id=bot_instance_id,
                is_running=True,
                details=details,
                trace_id=trace_id,
            )

        state.is_running = True
        state.details = details or state.details
        state.trace_id = trace_id or state.trace_id
        state.updated_at = self._utc_now()
        self.session.add(state)
        self.session.flush()
        return state

    def update_status(
        self,
        bot_instance_id: uuid.UUID,
        status: str,
        stopped_at: datetime | None = None,
    ) -> BotInstance | None:
        entity = self.session.get(BotInstance, bot_instance_id)
        if entity is None:
            return None

        entity.status = status
        if stopped_at is not None:
            entity.stopped_at = stopped_at
        self.session.add(entity)
        self.session.flush()
        return entity

    def get_latest_active_bot(self) -> BotInstance | None:
        stmt = (
            select(BotInstance)
            .where(BotInstance.status.in_(["starting", "running"]))
            .order_by(BotInstance.started_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_runtime_state(self, bot_instance_id: uuid.UUID) -> BotRuntimeState | None:
        stmt = (
            select(BotRuntimeState)
            .where(BotRuntimeState.bot_instance_id == bot_instance_id)
            .order_by(BotRuntimeState.updated_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def upsert_runtime_state(
        self,
        bot_instance_id: uuid.UUID,
        is_running: bool,
        is_rejected: bool = False,
        rejection_reason: str | None = None,
        trace_id: uuid.UUID | None = None,
        context_snapshot: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
    ) -> BotRuntimeState:
        state = self.get_runtime_state(bot_instance_id)
        if state is None:
            state = BotRuntimeState(
                bot_instance_id=bot_instance_id,
                is_running=is_running,
                is_rejected=is_rejected,
                rejection_reason=rejection_reason,
                trace_id=trace_id,
                context_snapshot=context_snapshot or {},
                details=details or {},
            )
        else:
            state.is_running = is_running
            state.is_rejected = is_rejected
            state.rejection_reason = rejection_reason
            state.trace_id = trace_id
            state.context_snapshot = context_snapshot or state.context_snapshot
            state.details = details or state.details
            state.updated_at = self._utc_now()

        self.session.add(state)
        self.session.flush()
        return state

    def create_engine_run(
        self,
        trace_id: uuid.UUID,
        engine_name: str,
        status: str,
        bot_instance_id: uuid.UUID | None = None,
        input_reference: dict[str, Any] | None = None,
        output_reference: dict[str, Any] | None = None,
        duration_ms: int = 0,
        error_message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> EngineRun:
        entity = EngineRun(
            bot_instance_id=bot_instance_id,
            trace_id=trace_id,
            engine_name=engine_name,
            status=status,
            input_reference=input_reference or {},
            output_reference=output_reference or {},
            duration_ms=duration_ms,
            error_message=error_message,
            details=details or {},
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def mark_stale_engine_runs_interrupted(self, max_age_minutes: int = 15) -> int:
        """Mark orphan RUNNING engine rows as INTERRUPTED for safer recovery."""

        cutoff = self._utc_now() - timedelta(minutes=max_age_minutes)
        running_rows = list(
            self.session.execute(
                select(EngineRun).where(EngineRun.status == "RUNNING", EngineRun.created_at <= cutoff)
            ).scalars().all()
        )
        interrupted = 0
        terminal_statuses = ("SUCCESS", "FAILED", "REJECTED", "INTERRUPTED")

        for row in running_rows:
            has_terminal = self.session.execute(
                select(EngineRun.id)
                .where(
                    and_(
                        EngineRun.trace_id == row.trace_id,
                        EngineRun.engine_name == row.engine_name,
                        EngineRun.created_at > row.created_at,
                        EngineRun.status.in_(terminal_statuses),
                    )
                )
                .limit(1)
            ).scalar_one_or_none()
            if has_terminal is not None:
                continue

            row.status = "INTERRUPTED"
            row.error_message = row.error_message or "Marked interrupted by runtime recovery"
            self.session.add(row)
            interrupted += 1

        if interrupted > 0:
            self.session.flush()
        return interrupted
