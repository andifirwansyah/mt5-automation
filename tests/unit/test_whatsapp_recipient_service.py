from __future__ import annotations

from src.infrastructure.notification.models import NotificationEventType
from src.services.whatsapp_recipient_service import WhatsappRecipientService


def test_whatsapp_recipient_service_normalizes_phone_number() -> None:
    normalized = WhatsappRecipientService.normalize_phone_number("+62 812-3456-7890")
    assert normalized == "6281234567890"
    assert WhatsappRecipientService.to_chat_id(normalized) == "6281234567890@c.us"


def test_whatsapp_recipient_service_rejects_invalid_event_type() -> None:
    try:
        WhatsappRecipientService._validate_event_types([NotificationEventType.SIGNAL_READY.value, "INVALID_EVENT"])
    except ValueError as exc:
        assert "INVALID_EVENT" in str(exc)
    else:
        raise AssertionError("Invalid event type should be rejected")
