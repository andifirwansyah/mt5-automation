from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import inspect

from src.api.main import app
from src.config.settings import get_settings
from src.infrastructure.database.base import TRADING_SCHEMA
from src.infrastructure.database.models.notification_models import NotificationRecipient, NotificationSubscription
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


def _ensure_notification_tables() -> None:
    bind = SessionLocal.kw["bind"]
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names(schema=TRADING_SCHEMA))
    if "notification_recipients" not in existing_tables:
        NotificationRecipient.__table__.create(bind=bind, checkfirst=True)
    if "notification_subscriptions" not in existing_tables:
        NotificationSubscription.__table__.create(bind=bind, checkfirst=True)


def test_whatsapp_recipient_routes_require_authentication(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    get_settings.cache_clear()
    _ensure_notification_tables()
    try:
        client = TestClient(app)
        response = client.get("/api/v1/notifications/whatsapp/recipients")
        assert response.status_code == 401
    finally:
        get_settings.cache_clear()


def test_whatsapp_recipient_create_list_and_update_api(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    monkeypatch.setenv("WAHA_DEFAULT_SESSION", "default")
    get_settings.cache_clear()
    _ensure_notification_tables()

    login_email = f"dashboard.notification.{uuid.uuid4().hex[:10]}@example.com"
    login_password = "Pass123."
    unique_phone = f"62812{uuid.uuid4().int % 10**8:08d}"
    _create_dashboard_user(login_email, login_password)

    client = TestClient(app)
    headers = _login_and_get_auth_headers(client, login_email, login_password)

    create_response = client.post(
        "/api/v1/notifications/whatsapp/recipients",
        json={
            "display_name": "Ops WA",
            "phone_number": f"+{unique_phone}",
            "session_name": "default",
            "is_active": True,
            "subscribed_events": ["SIGNAL_READY", "DAILY_SUMMARY"],
            "metadata": {"team": "ops"},
        },
        headers=headers,
    )

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["display_name"] == "Ops WA"
    assert created["phone_number"] == unique_phone
    assert created["chat_id"] == f"{unique_phone}@c.us"
    assert created["subscribed_events"] == ["DAILY_SUMMARY", "SIGNAL_READY"]

    recipient_id = created["id"]

    detail_response = client.get(f"/api/v1/notifications/whatsapp/recipients/{recipient_id}", headers=headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["metadata"]["team"] == "ops"

    list_response = client.get("/api/v1/notifications/whatsapp/recipients", headers=headers)
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert any(item["id"] == recipient_id for item in items)

    update_response = client.put(
        f"/api/v1/notifications/whatsapp/recipients/{recipient_id}",
        json={
            "display_name": "Ops WA Updated",
            "subscribed_events": ["TRADE_OPENED", "TRADE_CLOSED", "DAILY_SUMMARY"],
            "is_active": False,
        },
        headers=headers,
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["display_name"] == "Ops WA Updated"
    assert updated["is_active"] is False
    assert updated["subscribed_events"] == ["DAILY_SUMMARY", "TRADE_CLOSED", "TRADE_OPENED"]


def test_whatsapp_recipient_create_rejects_duplicate_number_same_session(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    monkeypatch.setenv("WAHA_DEFAULT_SESSION", "default")
    get_settings.cache_clear()
    _ensure_notification_tables()

    login_email = f"dashboard.notification.{uuid.uuid4().hex[:10]}@example.com"
    login_password = "Pass123."
    unique_phone = f"62811{uuid.uuid4().int % 10**8:08d}"
    _create_dashboard_user(login_email, login_password)

    client = TestClient(app)
    headers = _login_and_get_auth_headers(client, login_email, login_password)

    payload = {
        "display_name": "Ops Duplicate",
        "phone_number": unique_phone,
        "session_name": "default",
        "subscribed_events": ["SIGNAL_READY"],
    }
    first = client.post("/api/v1/notifications/whatsapp/recipients", json=payload, headers=headers)
    assert first.status_code == 200

    duplicate = client.post("/api/v1/notifications/whatsapp/recipients", json=payload, headers=headers)
    assert duplicate.status_code == 422
