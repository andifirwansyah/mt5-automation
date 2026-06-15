from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routes import notification_routes
from src.config.settings import get_settings
from src.infrastructure.database.session import SessionLocal
from src.repositories.auth_repository import AuthRepository
from src.services.password_hasher_service import hash_password


def _create_dashboard_user(email: str, password: str) -> None:
    session = SessionLocal()
    try:
        password_result = hash_password(password)
        AuthRepository(session).create_dashboard_user(
            email=email,
            password_hash=password_result.password_hash,
            password_salt=password_result.password_salt,
            hash_algorithm=password_result.hash_algorithm,
            hash_iterations=password_result.hash_iterations,
            is_active=True,
            metadata={"created_by": "pytest"},
        )
        session.commit()
    finally:
        session.close()


def _login_and_get_auth_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_whatsapp_recipient_test_message_and_dispatch_api(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    get_settings.cache_clear()

    login_email = f"dashboard.notification.{uuid.uuid4().hex[:10]}@example.com"
    login_password = "Pass123."
    _create_dashboard_user(login_email, login_password)

    class FakeDispatchService:
        def send_test_message(self, *, recipient_id, message: str):
            assert str(recipient_id) == "11111111-1111-1111-1111-111111111111"
            assert message == "hello ops"
            return type(
                "Result",
                (),
                {
                    "delivery_id": uuid.uuid4(),
                    "retry_of_delivery_id": None,
                    "attempt_number": 1,
                    "recipient_id": recipient_id,
                    "chat_id": "628123@c.us",
                    "session_name": "default",
                    "provider_message_id": "msg-1",
                    "status": "queued",
                    "text": message,
                    "narrative_provider": "manual_text",
                    "used_fallback": False,
                    "event_type": None,
                    "error_message": None,
                },
            )()

        def dispatch_event(self, *, event_type, payload, recipient_ids=None):
            assert event_type.value == "SIGNAL_READY"
            assert payload["symbol"] == "XAUUSD"
            return [
                type(
                    "Result",
                    (),
                    {
                        "delivery_id": uuid.uuid4(),
                        "retry_of_delivery_id": None,
                        "attempt_number": 1,
                        "recipient_id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
                        "chat_id": "628123@c.us",
                        "session_name": "default",
                        "provider_message_id": "msg-2",
                        "status": "queued",
                        "text": "rendered message",
                        "narrative_provider": "groq",
                        "used_fallback": False,
                        "event_type": "SIGNAL_READY",
                        "error_message": None,
                    },
                )()
            ]

    monkeypatch.setattr(notification_routes, "_whatsapp_dispatch_service", lambda db: FakeDispatchService())

    try:
        client = TestClient(app)
        headers = _login_and_get_auth_headers(client, login_email, login_password)

        test_response = client.post(
            "/api/v1/notifications/whatsapp/recipients/11111111-1111-1111-1111-111111111111/test-message",
            json={"message": "hello ops"},
            headers=headers,
        )
        assert test_response.status_code == 200
        assert test_response.json()["total_sent"] == 1
        assert test_response.json()["results"][0]["status"] == "queued"

        dispatch_response = client.post(
            "/api/v1/notifications/whatsapp/dispatch",
            json={
                "event_type": "SIGNAL_READY",
                "payload": {
                    "symbol": "XAUUSD",
                    "direction": "BUY",
                    "entry_price": 2345.1,
                    "stop_loss": 2339.5,
                    "take_profit": 2354.8,
                    "strategy": "EMA_ATR_TREND",
                },
            },
            headers=headers,
        )
        assert dispatch_response.status_code == 200
        assert dispatch_response.json()["event_type"] == "SIGNAL_READY"
        assert dispatch_response.json()["total_sent"] == 1
        assert dispatch_response.json()["results"][0]["narrative_provider"] == "groq"

        empty_dispatch_response = client.post(
            "/api/v1/notifications/whatsapp/dispatch",
            json={
                "event_type": "SIGNAL_READY",
                "payload": {"symbol": "XAUUSD"},
                "recipient_ids": [],
            },
            headers=headers,
        )
        assert empty_dispatch_response.status_code == 200
        assert empty_dispatch_response.json()["total_sent"] == 0
    finally:
        get_settings.cache_clear()


def test_whatsapp_delivery_history_api(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    get_settings.cache_clear()

    login_email = f"dashboard.notification.{uuid.uuid4().hex[:10]}@example.com"
    login_password = "Pass123."
    _create_dashboard_user(login_email, login_password)

    created_at = "2026-06-15T13:00:00+00:00"

    class FakeRepository:
        def list_deliveries(self, **kwargs):
            return [
                type(
                    "Delivery",
                    (),
                    {
                        "id": uuid.uuid4(),
                        "recipient_id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
                        "retry_of_delivery_id": None,
                        "attempt_number": 1,
                        "event_type": "SIGNAL_READY",
                        "provider_name": "WWEB",
                        "session_name": "default",
                        "destination": "628123@c.us",
                        "status": "queued",
                        "provider_message_id": "msg-2",
                        "narrative_provider": "groq",
                        "used_fallback": False,
                        "message_text": "rendered message",
                        "error_message": None,
                        "details": {"status": "queued"},
                        "created_at": __import__("datetime").datetime.fromisoformat(created_at),
                    },
                )()
            ]

        def count_deliveries(self, **kwargs):
            return 1

    monkeypatch.setattr(notification_routes, "NotificationRepository", lambda db: FakeRepository())

    try:
        client = TestClient(app)
        headers = _login_and_get_auth_headers(client, login_email, login_password)
        response = client.get("/api/v1/notifications/whatsapp/deliveries?event_type=SIGNAL_READY", headers=headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["event_type"] == "SIGNAL_READY"
        assert payload["items"][0]["provider_name"] == "WWEB"
    finally:
        get_settings.cache_clear()


def test_whatsapp_retry_delivery_api(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    get_settings.cache_clear()

    login_email = f"dashboard.notification.{uuid.uuid4().hex[:10]}@example.com"
    login_password = "Pass123."
    _create_dashboard_user(login_email, login_password)

    retry_of_id = uuid.UUID("11111111-1111-1111-1111-111111111111")

    class FakeDispatchService:
        def retry_delivery(self, *, delivery_id):
            assert delivery_id == retry_of_id
            return type(
                "Result",
                (),
                {
                    "delivery_id": uuid.uuid4(),
                    "retry_of_delivery_id": retry_of_id,
                    "attempt_number": 2,
                    "recipient_id": uuid.UUID("22222222-2222-2222-2222-222222222222"),
                    "chat_id": "628123@c.us",
                    "session_name": "default",
                    "provider_message_id": "msg-retry",
                    "status": "queued",
                    "text": "previous rendered message",
                    "narrative_provider": "groq",
                    "used_fallback": False,
                    "event_type": "SIGNAL_READY",
                    "error_message": None,
                },
            )()

    monkeypatch.setattr(notification_routes, "_whatsapp_dispatch_service", lambda db: FakeDispatchService())

    try:
        client = TestClient(app)
        headers = _login_and_get_auth_headers(client, login_email, login_password)
        response = client.post(f"/api/v1/notifications/whatsapp/deliveries/{retry_of_id}/retry", headers=headers)
        assert response.status_code == 200
        payload = response.json()["delivery"]
        assert payload["attempt_number"] == 2
        assert payload["retry_of_delivery_id"] == str(retry_of_id)
    finally:
        get_settings.cache_clear()


def test_whatsapp_delivery_detail_and_retry_candidates_api(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    monkeypatch.setenv("NOTIFICATION_RETRY_ENABLED", "true")
    monkeypatch.setenv("NOTIFICATION_RETRY_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("NOTIFICATION_RETRY_BATCH_LIMIT", "25")
    get_settings.cache_clear()

    login_email = f"dashboard.notification.{uuid.uuid4().hex[:10]}@example.com"
    login_password = "Pass123."
    _create_dashboard_user(login_email, login_password)

    delivery_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    created_at = __import__("datetime").datetime.fromisoformat("2026-06-15T13:00:00+00:00")

    class FakeRepository:
        def get_delivery_by_id(self, requested_delivery_id):
            if requested_delivery_id != delivery_id:
                return None
            return type(
                "Delivery",
                (),
                {
                    "id": delivery_id,
                    "recipient_id": uuid.UUID("22222222-2222-2222-2222-222222222222"),
                    "retry_of_delivery_id": None,
                    "attempt_number": 1,
                    "event_type": "SIGNAL_READY",
                    "provider_name": "WWEB",
                    "session_name": "default",
                    "destination": "628123@c.us",
                    "status": "failed",
                    "provider_message_id": None,
                    "narrative_provider": "groq",
                    "used_fallback": False,
                    "message_text": "rendered message",
                    "error_message": "wweb down",
                    "details": {"status": "failed"},
                    "created_at": created_at,
                },
            )()

    class FakeDispatchService:
        def list_retry_candidates(self):
            return [FakeRepository().get_delivery_by_id(delivery_id)]

    monkeypatch.setattr(notification_routes, "NotificationRepository", lambda db: FakeRepository())
    monkeypatch.setattr(notification_routes, "_whatsapp_dispatch_service", lambda db: FakeDispatchService())

    try:
        client = TestClient(app)
        headers = _login_and_get_auth_headers(client, login_email, login_password)

        detail_response = client.get(f"/api/v1/notifications/whatsapp/deliveries/{delivery_id}", headers=headers)
        assert detail_response.status_code == 200
        assert detail_response.json()["status"] == "failed"

        candidates_response = client.get("/api/v1/notifications/whatsapp/deliveries/retry-candidates", headers=headers)
        assert candidates_response.status_code == 200
        payload = candidates_response.json()
        assert payload["policy"]["enabled"] is True
        assert payload["policy"]["max_attempts"] == 4
        assert payload["policy"]["batch_limit"] == 25
        assert payload["total"] == 1
        assert payload["items"][0]["id"] == str(delivery_id)
    finally:
        get_settings.cache_clear()
