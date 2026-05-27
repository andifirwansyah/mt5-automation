"""Service for periodic runtime heartbeat updates."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

from loguru import logger

from src.repositories.bot_repository import BotRepository


class HeartbeatService:
    """Background heartbeat loop that updates runtime state in DB."""

    def __init__(self, bot_repository: BotRepository, bot_instance_id: uuid.UUID, interval_seconds: float = 5.0) -> None:
        self.bot_repository = bot_repository
        self.bot_instance_id = bot_instance_id
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                now = self._utc_now().isoformat()
                self.bot_repository.update_heartbeat(
                    bot_instance_id=self.bot_instance_id,
                    details={"last_heartbeat_at": now},
                )
                self.bot_repository.session.commit()
            except Exception:
                logger.exception("Heartbeat loop failed")
                self.bot_repository.session.rollback()

            self._stop_event.wait(self.interval_seconds)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="heartbeat-loop", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
