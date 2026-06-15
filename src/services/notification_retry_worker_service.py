"""Background worker foundation for automatic notification retry processing."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from src.config.settings import AppSettings
from src.infrastructure.notification import GroqNarratorClient, WahaClient
from src.repositories.notification_repository import NotificationRepository
from src.services.notification_message_builder import NotificationMessageBuilder
from src.services.notification_narrator_service import NotificationNarratorService
from src.services.whatsapp_dispatch_service import WhatsappDispatchService


@dataclass(frozen=True, slots=True)
class NotificationRetryCycleResult:
    exhausted_count: int
    retried_count: int
    failed_retry_count: int


class NotificationRetryWorkerService:
    """Periodic background worker that retries failed notification deliveries."""

    def __init__(self, session_factory: Callable[[], Session], settings: AppSettings) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.interval_seconds = max(1.0, settings.notification_retry_loop_interval_seconds)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _build_dispatch_service(self, session: Session) -> WhatsappDispatchService:
        narrator_client = None
        if self.settings.notification_ai_enabled and self.settings.groq_secret_key.strip():
            narrator_client = GroqNarratorClient(
                base_url=self.settings.groq_base_url,
                api_key=self.settings.groq_secret_key,
                model=self.settings.groq_model,
                timeout_seconds=self.settings.groq_request_timeout_seconds,
            )
        return WhatsappDispatchService(
            repository=NotificationRepository(session),
            waha_client=WahaClient(
                base_url=self.settings.waha_base_url,
                api_key=self.settings.waha_api_key,
                default_session=self.settings.waha_default_session,
                timeout_seconds=self.settings.waha_request_timeout_seconds,
            ),
            message_builder=NotificationMessageBuilder(),
            narrator_service=NotificationNarratorService(
                client=narrator_client,
                enabled=self.settings.notification_ai_enabled and bool(self.settings.groq_secret_key.strip()),
                max_sentences=self.settings.notification_ai_max_sentences,
            ),
            retry_enabled=self.settings.notification_retry_enabled,
            retry_max_attempts=self.settings.notification_retry_max_attempts,
            retry_batch_limit=self.settings.notification_retry_batch_limit,
            retry_backoff_base_seconds=self.settings.notification_retry_backoff_base_seconds,
            retry_backoff_multiplier=self.settings.notification_retry_backoff_multiplier,
            retry_backoff_max_seconds=self.settings.notification_retry_backoff_max_seconds,
        )

    def sync_once(self) -> NotificationRetryCycleResult:
        session = self.session_factory()
        try:
            service = self._build_dispatch_service(session)
            exhausted_count = service.mark_exhausted_deliveries()
            session.commit()

            retried_count = 0
            failed_retry_count = 0
            candidates = service.list_retry_candidates()
            for candidate in candidates:
                try:
                    service.retry_delivery(delivery_id=candidate.id)
                    session.commit()
                    retried_count += 1
                except Exception:
                    logger.exception("Notification retry worker failed for delivery_id={}", candidate.id)
                    session.commit()
                    failed_retry_count += 1

            return NotificationRetryCycleResult(
                exhausted_count=exhausted_count,
                retried_count=retried_count,
                failed_retry_count=failed_retry_count,
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.sync_once()
            except Exception:
                logger.exception("Notification retry worker loop failed")
            self._stop_event.wait(self.interval_seconds)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="notification-retry-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
