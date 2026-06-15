from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.infrastructure.database.models import NotificationRecipient
from src.infrastructure.notification.models import NotificationEventType, NotificationNarrativeResult
from src.services.notification_message_builder import NotificationMessageBuilder
from src.services.whatsapp_dispatch_service import WhatsappDispatchService


class FakeRepo:
    def __init__(self, recipient: NotificationRecipient) -> None:
        self.recipient = recipient
        self.deliveries: list[dict] = []

    def get_recipient_by_id(self, recipient_id: uuid.UUID):
        return self.recipient if recipient_id == self.recipient.id else None

    def list_recipients_by_event(self, **kwargs):
        return [self.recipient]

    def create_delivery(self, **kwargs):
        self.deliveries.append(kwargs)
        return type("Delivery", (), {"id": uuid.uuid4()})()

    def get_delivery_by_id(self, delivery_id: uuid.UUID):
        return getattr(self, "delivery_row", None)


class FakeWahaClient:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail

    def send_text_message(self, *, chat_id: str, text: str, session: str | None = None):
        if self.should_fail:
            raise RuntimeError("waha down")
        return {"id": "msg-1", "status": "queued", "chatId": chat_id, "session": session, "text": text}


class FakeNarrator:
    def narrate(self, payload):
        return NotificationNarrativeResult(
            narrative="Narasi singkat dari AI.",
            used_fallback=False,
            provider="groq",
        )


def _build_recipient() -> NotificationRecipient:
    return NotificationRecipient(
        id=uuid.uuid4(),
        channel_type="WHATSAPP",
        display_name="Ops",
        destination="6281234567890@c.us",
        session_name="default",
        is_active=True,
        metadata_json={"phone_number": "6281234567890"},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_whatsapp_dispatch_service_send_test_message() -> None:
    recipient = _build_recipient()
    service = WhatsappDispatchService(
        repository=FakeRepo(recipient),
        waha_client=FakeWahaClient(),
        message_builder=NotificationMessageBuilder(),
        narrator_service=FakeNarrator(),
    )

    result = service.send_test_message(recipient_id=recipient.id, message="hello ops")

    assert result.chat_id == "6281234567890@c.us"
    assert result.status == "queued"
    assert result.narrative_provider == "manual_text"
    assert result.delivery_id is not None
    assert result.attempt_number == 1


def test_whatsapp_dispatch_service_dispatch_event_renders_message() -> None:
    recipient = _build_recipient()
    service = WhatsappDispatchService(
        repository=FakeRepo(recipient),
        waha_client=FakeWahaClient(),
        message_builder=NotificationMessageBuilder(),
        narrator_service=FakeNarrator(),
    )

    results = service.dispatch_event(
        event_type=NotificationEventType.SIGNAL_READY,
        payload={
            "symbol": "XAUUSD",
            "direction": "BUY",
            "entry_price": 2345.1,
            "stop_loss": 2339.5,
            "take_profit": 2354.8,
            "strategy": "EMA_ATR_TREND",
        },
    )

    assert len(results) == 1
    assert "📡 Signal Ready" in results[0].text
    assert "Narasi singkat dari AI." in results[0].text
    assert results[0].narrative_provider == "groq"
    assert results[0].attempt_number == 1


def test_whatsapp_dispatch_service_records_failed_delivery() -> None:
    recipient = _build_recipient()
    repo = FakeRepo(recipient)
    service = WhatsappDispatchService(
        repository=repo,
        waha_client=FakeWahaClient(should_fail=True),
        message_builder=NotificationMessageBuilder(),
        narrator_service=FakeNarrator(),
    )

    try:
        service.send_test_message(recipient_id=recipient.id, message="hello ops")
    except RuntimeError as exc:
        assert "waha down" in str(exc)
    else:
        raise AssertionError("Expected WAHA failure")

    assert repo.deliveries[-1]["status"] == "failed"
    assert repo.deliveries[-1]["error_message"] == "waha down"


def test_whatsapp_dispatch_service_retry_failed_delivery() -> None:
    recipient = _build_recipient()
    repo = FakeRepo(recipient)
    failed_delivery_id = uuid.uuid4()
    repo.delivery_row = type(
        "DeliveryRow",
        (),
        {
            "id": failed_delivery_id,
            "recipient_id": recipient.id,
            "event_type": "SIGNAL_READY",
            "status": "failed",
            "message_text": "previous rendered message",
            "used_fallback": False,
            "narrative_provider": "groq",
            "attempt_number": 1,
        },
    )()
    service = WhatsappDispatchService(
        repository=repo,
        waha_client=FakeWahaClient(),
        message_builder=NotificationMessageBuilder(),
        narrator_service=FakeNarrator(),
    )

    result = service.retry_delivery(delivery_id=failed_delivery_id)

    assert result.retry_of_delivery_id == failed_delivery_id
    assert result.attempt_number == 2
    assert repo.deliveries[-1]["retry_of_delivery_id"] == failed_delivery_id


def test_whatsapp_dispatch_service_respects_retry_max_attempts() -> None:
    recipient = _build_recipient()
    repo = FakeRepo(recipient)
    failed_delivery_id = uuid.uuid4()
    repo.delivery_row = type(
        "DeliveryRow",
        (),
        {
            "id": failed_delivery_id,
            "recipient_id": recipient.id,
            "event_type": "SIGNAL_READY",
            "status": "failed",
            "message_text": "previous rendered message",
            "used_fallback": False,
            "narrative_provider": "groq",
            "attempt_number": 3,
        },
    )()
    service = WhatsappDispatchService(
        repository=repo,
        waha_client=FakeWahaClient(),
        message_builder=NotificationMessageBuilder(),
        narrator_service=FakeNarrator(),
        retry_max_attempts=3,
    )

    try:
        service.retry_delivery(delivery_id=failed_delivery_id)
    except ValueError as exc:
        assert "max retry attempts" in str(exc).lower()
    else:
        raise AssertionError("Expected retry max attempts guard")


def test_whatsapp_dispatch_service_lists_retry_candidates() -> None:
    recipient = _build_recipient()
    repo = FakeRepo(recipient)
    expected = [object(), object()]
    repo.list_retry_candidates = lambda **kwargs: expected
    service = WhatsappDispatchService(
        repository=repo,
        waha_client=FakeWahaClient(),
        message_builder=NotificationMessageBuilder(),
        narrator_service=FakeNarrator(),
        retry_enabled=True,
        retry_max_attempts=4,
        retry_batch_limit=25,
    )

    items = service.list_retry_candidates()

    assert items == expected


def test_whatsapp_dispatch_service_marks_final_failed_attempt_as_exhausted() -> None:
    recipient = _build_recipient()
    repo = FakeRepo(recipient)
    service = WhatsappDispatchService(
        repository=repo,
        waha_client=FakeWahaClient(should_fail=True),
        message_builder=NotificationMessageBuilder(),
        narrator_service=FakeNarrator(),
        retry_enabled=True,
        retry_max_attempts=3,
    )

    try:
        service._send_text(
            recipient=recipient,
            text="hello ops",
            narrative=None,
            event_type="SIGNAL_READY",
            attempt_number=3,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected failure on final retry attempt")

    assert repo.deliveries[-1]["status"] == "exhausted"


def test_whatsapp_dispatch_service_rejects_inactive_test_message() -> None:
    recipient = _build_recipient()
    recipient.is_active = False
    service = WhatsappDispatchService(
        repository=FakeRepo(recipient),
        waha_client=FakeWahaClient(),
        message_builder=NotificationMessageBuilder(),
        narrator_service=FakeNarrator(),
    )

    try:
        service.send_test_message(recipient_id=recipient.id, message="hello ops")
    except ValueError as exc:
        assert "inactive" in str(exc).lower()
    else:
        raise AssertionError("Inactive recipient should be rejected")
