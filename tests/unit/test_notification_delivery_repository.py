from __future__ import annotations

import uuid

from src.repositories.notification_repository import NotificationRepository


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flushed = False

    def add(self, entity: object) -> None:
        self.added.append(entity)

    def flush(self) -> None:
        self.flushed = True


def test_notification_repository_create_delivery_stores_entity() -> None:
    session = FakeSession()
    repo = NotificationRepository(session)  # type: ignore[arg-type]

    delivery = repo.create_delivery(
        recipient_id=uuid.uuid4(),
        event_type="SIGNAL_READY",
        provider_name="WWEB",
        session_name="default",
        destination="628123@c.us",
        status="queued",
        provider_message_id="msg-1",
        narrative_provider="groq",
        used_fallback=False,
        message_text="hello",
        details={"id": "msg-1"},
    )

    assert delivery.provider_name == "WWEB"
    assert delivery.status == "queued"
    assert delivery.attempt_number == 1
    assert session.flushed is True
    assert session.added
