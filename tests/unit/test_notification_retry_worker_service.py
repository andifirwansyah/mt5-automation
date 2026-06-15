from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.config.settings import AppSettings
from src.services.notification_retry_worker_service import NotificationRetryCycleResult, NotificationRetryWorkerService
from src.services.whatsapp_dispatch_service import WhatsappDispatchService


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeCandidate:
    id: object


class FakeDispatchService:
    def __init__(self) -> None:
        self.exhausted_called = False
        self.retry_calls: list[object] = []
        self.candidates = [FakeCandidate(id="delivery-1"), FakeCandidate(id="delivery-2")]

    def mark_exhausted_deliveries(self) -> int:
        self.exhausted_called = True
        return 1

    def list_retry_candidates(self):
        return self.candidates

    def retry_delivery(self, *, delivery_id):
        self.retry_calls.append(delivery_id)
        if delivery_id == "delivery-2":
            raise RuntimeError("retry failed")


def test_whatsapp_dispatch_service_backoff_and_due_filtering() -> None:
    service = WhatsappDispatchService(
        repository=object(),  # type: ignore[arg-type]
        wweb_client=object(),  # type: ignore[arg-type]
        message_builder=object(),  # type: ignore[arg-type]
        narrator_service=object(),  # type: ignore[arg-type]
        retry_backoff_base_seconds=60,
        retry_backoff_multiplier=2,
        retry_backoff_max_seconds=300,
    )

    assert service.compute_retry_delay_seconds(attempt_number=1) == 60
    assert service.compute_retry_delay_seconds(attempt_number=2) == 120
    assert service.compute_retry_delay_seconds(attempt_number=10) == 300

    now = datetime.now(timezone.utc)
    due_delivery = type("Delivery", (), {"created_at": now - timedelta(seconds=70), "attempt_number": 1})()
    not_due_delivery = type("Delivery", (), {"created_at": now - timedelta(seconds=30), "attempt_number": 1})()

    assert service._is_retry_due(due_delivery, now=now) is True
    assert service._is_retry_due(not_due_delivery, now=now) is False


def test_notification_retry_worker_sync_once_counts_results(monkeypatch) -> None:
    session = FakeSession()
    fake_dispatch = FakeDispatchService()
    settings = AppSettings()
    worker = NotificationRetryWorkerService(session_factory=lambda: session, settings=settings)
    monkeypatch.setattr(worker, "_build_dispatch_service", lambda _: fake_dispatch)

    result = worker.sync_once()

    assert isinstance(result, NotificationRetryCycleResult)
    assert result.exhausted_count == 1
    assert result.retried_count == 1
    assert result.failed_retry_count == 1
    assert session.commit_count == 3
    assert session.closed is True
