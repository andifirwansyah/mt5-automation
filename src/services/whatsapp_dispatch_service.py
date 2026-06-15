"""Manual WhatsApp dispatch service for test messages and event-based sends."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from src.infrastructure.database.models import NotificationRecipient
from src.infrastructure.notification import (
    NotificationEventType,
    NotificationNarrativeResult,
    RenderedNotificationMessage,
    WwebClient,
)
from src.repositories.notification_repository import NotificationRepository
from src.services.notification_message_builder import NotificationMessageBuilder
from src.services.notification_narrator_service import NotificationNarratorService
from src.services.whatsapp_recipient_service import WHATSAPP_CHANNEL_TYPE, WhatsappRecipientService

ERROR_MESSAGE_MAX_LENGTH = 1000


@dataclass(frozen=True, slots=True)
class WhatsappSendResult:
    recipient_id: uuid.UUID
    chat_id: str
    session_name: str
    provider_message_id: str | None
    status: str
    text: str
    narrative_provider: str
    used_fallback: bool
    event_type: str | None
    error_message: str | None
    delivery_id: uuid.UUID | None
    retry_of_delivery_id: uuid.UUID | None
    attempt_number: int


class WhatsappDispatchService:
    """Send manual WhatsApp notifications using registered recipients."""

    def __init__(
        self,
        *,
        repository: NotificationRepository,
        wweb_client: WwebClient,
        message_builder: NotificationMessageBuilder,
        narrator_service: NotificationNarratorService,
        retry_enabled: bool = True,
        retry_max_attempts: int = 3,
        retry_batch_limit: int = 100,
        retry_backoff_base_seconds: float = 60.0,
        retry_backoff_multiplier: float = 2.0,
        retry_backoff_max_seconds: float = 3600.0,
    ) -> None:
        self.repository = repository
        self.wweb_client = wweb_client
        self.message_builder = message_builder
        self.narrator_service = narrator_service
        self.retry_enabled = retry_enabled
        self.retry_max_attempts = max(1, retry_max_attempts)
        self.retry_batch_limit = max(1, retry_batch_limit)
        self.retry_backoff_base_seconds = max(1.0, retry_backoff_base_seconds)
        self.retry_backoff_multiplier = max(1.0, retry_backoff_multiplier)
        self.retry_backoff_max_seconds = max(self.retry_backoff_base_seconds, retry_backoff_max_seconds)

    def send_test_message(self, *, recipient_id: uuid.UUID, message: str) -> WhatsappSendResult:
        recipient = self.repository.get_recipient_by_id(recipient_id)
        if recipient is None or recipient.channel_type != WHATSAPP_CHANNEL_TYPE:
            raise ValueError("WhatsApp recipient not found")
        if not recipient.is_active:
            raise ValueError("WhatsApp recipient is inactive")
        if not message.strip():
            raise ValueError("message must not be empty")
        return self._send_text(recipient=recipient, text=message.strip(), narrative=None, event_type=None)

    def dispatch_event(
        self,
        *,
        event_type: NotificationEventType,
        payload: dict[str, Any],
        recipient_ids: list[uuid.UUID] | None = None,
        source_key: str | None = None,
    ) -> list[WhatsappSendResult]:
        recipients = self.repository.list_recipients_by_event(
            channel_type=WHATSAPP_CHANNEL_TYPE,
            event_type=event_type.value,
            recipient_ids=recipient_ids,
            active_only=True,
        )
        if source_key:
            sent_recipient_ids = set(
                self.repository.list_recipient_ids_with_source_delivery(
                    event_type=event_type.value,
                    source_key=source_key,
                )
            )
            recipients = [recipient for recipient in recipients if recipient.id not in sent_recipient_ids]
        rendered = self._render_event_message(event_type=event_type, payload=payload)
        return [
            self._send_text(
                recipient=recipient,
                text=rendered.text,
                narrative=rendered.narrative,
                event_type=event_type.value,
                source_key=source_key,
            )
            for recipient in recipients
        ]

    def retry_delivery(self, *, delivery_id: uuid.UUID) -> WhatsappSendResult:
        if not self.retry_enabled:
            raise ValueError("Notification retry is disabled")
        delivery = self.repository.get_delivery_by_id(delivery_id)
        if delivery is None:
            raise ValueError("Notification delivery not found")
        if delivery.status.lower() != "failed":
            raise ValueError("Only failed delivery can be retried")
        if int(delivery.attempt_number) >= self.retry_max_attempts:
            raise ValueError("Notification delivery has reached max retry attempts")
        recipient = self.repository.get_recipient_by_id(delivery.recipient_id)
        if recipient is None or recipient.channel_type != WHATSAPP_CHANNEL_TYPE:
            raise ValueError("WhatsApp recipient not found")
        if not recipient.is_active:
            raise ValueError("WhatsApp recipient is inactive")
        delivery_details = getattr(delivery, "details", {}) or {}
        return self._send_text(
            recipient=recipient,
            text=delivery.message_text,
            narrative=NotificationNarrativeResult(
                narrative=delivery.message_text,
                used_fallback=delivery.used_fallback,
                provider=delivery.narrative_provider,
            ),
            event_type=delivery.event_type,
            retry_of_delivery_id=delivery.id,
            attempt_number=int(delivery.attempt_number) + 1,
            source_key=delivery_details.get("source_key"),
        )

    def list_retry_candidates(self) -> list[NotificationRecipient | Any]:
        if not self.retry_enabled:
            return []
        candidates = self.repository.list_retry_candidates(
            max_attempts=self.retry_max_attempts,
            limit=self.retry_batch_limit,
        )
        now = datetime.now(timezone.utc)
        return [candidate for candidate in candidates if self._is_retry_due(candidate, now=now)]

    def mark_exhausted_deliveries(self) -> int:
        exhausted = self.repository.list_exhaustion_candidates(
            min_attempts=self.retry_max_attempts,
            limit=self.retry_batch_limit,
        )
        for delivery in exhausted:
            self.repository.update_delivery_status(
                delivery,
                status="exhausted",
                details_patch={"exhausted_at": datetime.now(timezone.utc).isoformat()},
            )
        return len(exhausted)

    def compute_retry_delay_seconds(self, *, attempt_number: int) -> float:
        exponent = max(0, attempt_number - 1)
        delay = self.retry_backoff_base_seconds * (self.retry_backoff_multiplier ** exponent)
        return min(delay, self.retry_backoff_max_seconds)

    def _is_retry_due(self, delivery: Any, *, now: datetime) -> bool:
        created_at = getattr(delivery, "created_at", None)
        if created_at is None:
            return True
        delay_seconds = self.compute_retry_delay_seconds(attempt_number=int(getattr(delivery, "attempt_number", 1)))
        return created_at + timedelta(seconds=delay_seconds) <= now

    def _render_event_message(self, *, event_type: NotificationEventType, payload: dict[str, Any]) -> RenderedNotificationMessage:
        structured_payload = self.message_builder.build_payload(event_type=event_type, payload=payload)
        narrative = self.narrator_service.narrate(structured_payload)
        return self.message_builder.render_message(structured_payload, narrative)

    def _send_text(
        self,
        *,
        recipient: NotificationRecipient,
        text: str,
        narrative: NotificationNarrativeResult | None,
        event_type: str | None,
        retry_of_delivery_id: uuid.UUID | None = None,
        attempt_number: int = 1,
        source_key: str | None = None,
    ) -> WhatsappSendResult:
        provider_message_id = None
        status = "submitted"
        error_message = None
        provider_response: dict[str, Any] | None = None
        caught_exception: Exception | None = None
        try:
            raw_response = self.wweb_client.send_text_message(
                chat_id=recipient.destination,
                text=text,
            )
            if isinstance(raw_response, dict):
                provider_response = raw_response
                provider_message_id = raw_response.get("id") or raw_response.get("messageId")
                if isinstance(provider_message_id, Mapping):
                    provider_message_id = provider_message_id.get("_serialized") or provider_message_id.get("id")
                status = str(raw_response.get("status") or status)
        except Exception as exc:
            status = "exhausted" if self.retry_enabled and attempt_number >= self.retry_max_attempts else "failed"
            error_message = str(exc)[:ERROR_MESSAGE_MAX_LENGTH]
            caught_exception = exc

        delivery = self.repository.create_delivery(
            recipient_id=recipient.id,
            event_type=event_type,
            provider_name="WWEB",
            session_name=recipient.session_name,
            destination=recipient.destination,
            status=status,
            provider_message_id=str(provider_message_id) if provider_message_id is not None else None,
            retry_of_delivery_id=retry_of_delivery_id,
            attempt_number=attempt_number,
            narrative_provider=(narrative.provider if narrative is not None else "manual_text"),
            used_fallback=(narrative.used_fallback if narrative is not None else False),
            message_text=text,
            error_message=error_message,
            details={**(provider_response or {}), **({"source_key": source_key} if source_key else {})},
        )
        if caught_exception is not None:
            raise caught_exception
        return WhatsappSendResult(
            recipient_id=recipient.id,
            chat_id=recipient.destination,
            session_name=recipient.session_name,
            provider_message_id=str(provider_message_id) if provider_message_id is not None else None,
            status=status,
            text=text,
            narrative_provider=(narrative.provider if narrative is not None else "manual_text"),
            used_fallback=(narrative.used_fallback if narrative is not None else False),
            event_type=event_type,
            error_message=error_message,
            delivery_id=delivery.id,
            retry_of_delivery_id=retry_of_delivery_id,
            attempt_number=attempt_number,
        )
