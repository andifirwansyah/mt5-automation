"""Service for bot runtime lifecycle updates."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from src.infrastructure.database.models import BotInstance
from src.repositories.bot_repository import BotRepository


class BotRuntimeService:
    """Manage bot instance registration and status transitions."""

    def __init__(self, bot_repository: BotRepository) -> None:
        self.bot_repository = bot_repository

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    def register_bot_instance(
        self,
        instance_name: str,
        host_name: str,
        process_id: int,
        metadata: dict[str, Any] | None = None,
    ) -> BotInstance:
        entity = self.bot_repository.create_bot_instance(
            instance_name=instance_name,
            host_name=host_name,
            process_id=process_id,
            status="starting",
            metadata=metadata,
            started_at=self._utc_now(),
        )
        self.bot_repository.session.commit()
        return entity

    def mark_running(self, bot_instance_id: uuid.UUID) -> None:
        self.bot_repository.update_status(bot_instance_id=bot_instance_id, status="running")
        self.bot_repository.upsert_runtime_state(
            bot_instance_id=bot_instance_id,
            is_running=True,
            is_rejected=False,
            rejection_reason=None,
            details={"status": "running", "updated_at": self._utc_now().isoformat()},
        )
        self.bot_repository.session.commit()

    def mark_stopped(self, bot_instance_id: uuid.UUID) -> None:
        now = self._utc_now()
        self.bot_repository.update_status(bot_instance_id=bot_instance_id, status="stopped", stopped_at=now)
        self.bot_repository.upsert_runtime_state(
            bot_instance_id=bot_instance_id,
            is_running=False,
            is_rejected=False,
            rejection_reason=None,
            details={"status": "stopped", "updated_at": now.isoformat()},
        )
        self.bot_repository.session.commit()

    def mark_error(self, bot_instance_id: uuid.UUID, error_message: str) -> None:
        now = self._utc_now()
        self.bot_repository.update_status(bot_instance_id=bot_instance_id, status="error", stopped_at=now)
        self.bot_repository.upsert_runtime_state(
            bot_instance_id=bot_instance_id,
            is_running=False,
            is_rejected=True,
            rejection_reason="RUNTIME_ERROR",
            details={"status": "error", "error_message": error_message, "updated_at": now.isoformat()},
        )
        self.bot_repository.session.commit()
