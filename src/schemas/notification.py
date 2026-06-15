"""Schemas for notification channel onboarding and WhatsApp session APIs."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.infrastructure.notification.models import NotificationEventType


class WhatsappSessionCreatePayload(BaseModel):
    session_name: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")
    start: bool = True
    metadata: dict[str, str] | None = None


class WhatsappSessionResponse(BaseModel):
    name: str
    status: str
    me: dict[str, Any] | None = None
    engine: dict[str, Any] | None = None
    config: dict[str, Any] | None = None


class WhatsappSessionListResponse(BaseModel):
    items: list[WhatsappSessionResponse]


class WhatsappQrCodeResponse(BaseModel):
    session_name: str
    format: Literal["image", "raw"]
    mimetype: str | None = None
    data: str | None = None
    value: str | None = None


class WhatsappRecipientCreatePayload(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    phone_number: str = Field(min_length=8, max_length=32)
    session_name: str | None = Field(default=None, min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")
    is_active: bool = True
    subscribed_events: list[NotificationEventType] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class WhatsappRecipientUpdatePayload(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone_number: str | None = Field(default=None, min_length=8, max_length=32)
    session_name: str | None = Field(default=None, min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")
    is_active: bool | None = None
    subscribed_events: list[NotificationEventType] | None = None
    metadata: dict[str, Any] | None = None


class WhatsappRecipientResponse(BaseModel):
    id: str
    channel_type: str
    display_name: str
    phone_number: str
    chat_id: str
    session_name: str
    is_active: bool
    subscribed_events: list[NotificationEventType]
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


class WhatsappRecipientListResponse(BaseModel):
    items: list[WhatsappRecipientResponse]
    total: int
    limit: int
    offset: int


class WhatsappTestMessagePayload(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class WhatsappDispatchPayload(BaseModel):
    event_type: NotificationEventType
    payload: dict[str, Any]
    recipient_ids: list[uuid.UUID] | None = None


class WhatsappDispatchResultResponse(BaseModel):
    delivery_id: str | None = None
    retry_of_delivery_id: str | None = None
    attempt_number: int
    recipient_id: str
    chat_id: str
    session_name: str
    provider_message_id: str | None = None
    status: str
    text: str
    narrative_provider: str
    used_fallback: bool
    event_type: NotificationEventType | None = None
    error_message: str | None = None


class WhatsappDispatchResponse(BaseModel):
    event_type: NotificationEventType | None = None
    total_sent: int
    results: list[WhatsappDispatchResultResponse]


class WhatsappDeliveryResponse(BaseModel):
    id: str
    recipient_id: str
    retry_of_delivery_id: str | None = None
    attempt_number: int
    event_type: NotificationEventType | None = None
    provider_name: str
    session_name: str
    destination: str
    status: str
    provider_message_id: str | None = None
    narrative_provider: str
    used_fallback: bool
    message_text: str
    error_message: str | None = None
    details: dict[str, Any]
    created_at: str


class WhatsappDeliveryListResponse(BaseModel):
    items: list[WhatsappDeliveryResponse]
    total: int
    limit: int
    offset: int


class WhatsappRetryDeliveryResponse(BaseModel):
    delivery: WhatsappDispatchResultResponse


class WhatsappRetryPolicyResponse(BaseModel):
    enabled: bool
    max_attempts: int
    batch_limit: int


class WhatsappRetryCandidateListResponse(BaseModel):
    policy: WhatsappRetryPolicyResponse
    items: list[WhatsappDeliveryResponse]
    total: int
