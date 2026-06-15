"""Service layer for WhatsApp recipient registry and subscriptions."""

from __future__ import annotations

import re
import uuid
from typing import Any

from src.infrastructure.database.models import NotificationRecipient, NotificationSubscription
from src.infrastructure.notification.models import NotificationEventType
from src.repositories.notification_repository import NotificationRepository

WHATSAPP_CHANNEL_TYPE = "WHATSAPP"
_PHONE_PATTERN = re.compile(r"\D+")


class WhatsappRecipientService:
    """Encapsulate normalization and subscription rules for WhatsApp recipients."""

    def __init__(self, repository: NotificationRepository, default_session_name: str) -> None:
        self.repository = repository
        self.default_session_name = default_session_name.strip() or "default"

    def list_recipients(self, *, limit: int, offset: int, include_inactive: bool) -> tuple[list[NotificationRecipient], int]:
        items = self.repository.list_recipients(
            channel_type=WHATSAPP_CHANNEL_TYPE,
            limit=limit,
            offset=offset,
            include_inactive=include_inactive,
        )
        total = self.repository.count_recipients(channel_type=WHATSAPP_CHANNEL_TYPE, include_inactive=include_inactive)
        return items, total

    def get_recipient(self, recipient_id: uuid.UUID) -> tuple[NotificationRecipient | None, list[NotificationSubscription]]:
        recipient = self.repository.get_recipient_by_id(recipient_id)
        subscriptions = self.repository.list_subscriptions(recipient_id, active_only=True) if recipient is not None else []
        return recipient, subscriptions

    def create_recipient(
        self,
        *,
        display_name: str,
        phone_number: str,
        session_name: str | None,
        is_active: bool,
        subscribed_events: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> tuple[NotificationRecipient, list[NotificationSubscription]]:
        normalized_session_name = self._normalize_session_name(session_name)
        normalized_phone_number = self.normalize_phone_number(phone_number)
        chat_id = self.to_chat_id(normalized_phone_number)
        self._validate_event_types(subscribed_events)

        existing = self.repository.get_recipient_by_channel_destination_session(
            channel_type=WHATSAPP_CHANNEL_TYPE,
            destination=chat_id,
            session_name=normalized_session_name,
        )
        if existing is not None:
            raise ValueError("WhatsApp recipient already exists for the same session and number")

        recipient = self.repository.create_recipient(
            channel_type=WHATSAPP_CHANNEL_TYPE,
            display_name=display_name.strip(),
            destination=chat_id,
            session_name=normalized_session_name,
            is_active=is_active,
            metadata=self._build_metadata(metadata, normalized_phone_number),
        )
        subscriptions = self.repository.replace_subscriptions(
            recipient_id=recipient.id,
            event_types=subscribed_events,
        )
        return recipient, subscriptions

    def update_recipient(
        self,
        recipient_id: uuid.UUID,
        *,
        display_name: str | None,
        phone_number: str | None,
        session_name: str | None,
        is_active: bool | None,
        subscribed_events: list[str] | None,
        metadata: dict[str, Any] | None,
    ) -> tuple[NotificationRecipient | None, list[NotificationSubscription]]:
        recipient = self.repository.get_recipient_by_id(recipient_id)
        if recipient is None:
            return None, []

        destination = None
        normalized_phone_number = None
        if phone_number is not None:
            normalized_phone_number = self.normalize_phone_number(phone_number)
            destination = self.to_chat_id(normalized_phone_number)
        normalized_session_name = self._normalize_session_name(session_name) if session_name is not None else None
        if subscribed_events is not None:
            self._validate_event_types(subscribed_events)

        candidate_destination = destination or recipient.destination
        candidate_session_name = normalized_session_name or recipient.session_name
        existing = self.repository.get_recipient_by_channel_destination_session(
            channel_type=WHATSAPP_CHANNEL_TYPE,
            destination=candidate_destination,
            session_name=candidate_session_name,
        )
        if existing is not None and existing.id != recipient.id:
            raise ValueError("WhatsApp recipient already exists for the same session and number")

        merged_metadata = self._merge_metadata(
            current=recipient.metadata_json,
            incoming=metadata,
            normalized_phone_number=normalized_phone_number,
        )
        recipient = self.repository.update_recipient(
            recipient,
            display_name=display_name.strip() if display_name is not None else None,
            destination=destination,
            session_name=normalized_session_name,
            is_active=is_active,
            metadata=merged_metadata,
        )
        subscriptions = self.repository.list_subscriptions(recipient.id, active_only=True)
        if subscribed_events is not None:
            subscriptions = self.repository.replace_subscriptions(recipient_id=recipient.id, event_types=subscribed_events)
        return recipient, subscriptions

    @staticmethod
    def normalize_phone_number(phone_number: str) -> str:
        digits_only = _PHONE_PATTERN.sub("", phone_number or "")
        if not digits_only or len(digits_only) < 8 or len(digits_only) > 20:
            raise ValueError("phone_number must contain 8-20 digits")
        return digits_only

    @staticmethod
    def to_chat_id(phone_number: str) -> str:
        return f"{phone_number}@c.us"

    @staticmethod
    def phone_number_from_chat_id(chat_id: str) -> str:
        return chat_id.removesuffix("@c.us")

    def _normalize_session_name(self, session_name: str | None) -> str:
        normalized = (session_name or self.default_session_name).strip()
        if not normalized:
            raise ValueError("session_name must not be empty")
        return normalized

    @staticmethod
    def _validate_event_types(event_types: list[str]) -> None:
        valid_values = {item.value for item in NotificationEventType}
        invalid = [item for item in event_types if item not in valid_values]
        if invalid:
            raise ValueError(f"Unsupported subscribed_events: {', '.join(sorted(invalid))}")

    @staticmethod
    def _build_metadata(metadata: dict[str, Any] | None, normalized_phone_number: str) -> dict[str, Any]:
        payload = dict(metadata or {})
        payload["phone_number"] = normalized_phone_number
        return payload

    @staticmethod
    def _merge_metadata(
        *,
        current: dict[str, Any],
        incoming: dict[str, Any] | None,
        normalized_phone_number: str | None,
    ) -> dict[str, Any]:
        payload = dict(current or {})
        if incoming is not None:
            payload = dict(incoming)
        if normalized_phone_number is not None:
            payload["phone_number"] = normalized_phone_number
        return payload
