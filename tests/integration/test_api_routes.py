from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from src.api.main import app
from src.config.settings import get_settings
from src.repositories.auth_repository import AuthRepository
from src.repositories.safety_repository import SafetyRepository
from src.infrastructure.database.session import SessionLocal
from src.services.password_hasher_service import hash_password


def test_fastapi_health_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"


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


def test_kill_switch_activate_deactivate_api(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    get_settings.cache_clear()
    session = SessionLocal()
    login_email = f"dashboard.user.{uuid.uuid4().hex[:10]}@example.com"
    login_password = "Pass123."
    try:
        _create_dashboard_user(login_email, login_password)
        repo = SafetyRepository(session)
        repo.deactivate_kill_switch(deactivated_by="test-pre-clean", details={"reason": "pre-clean"})
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    headers = _login_and_get_auth_headers(client, login_email, login_password)

    activate = client.post(
        "/api/v1/bot/kill-switch/activate",
        json={"reason": "test", "actor": "pytest"},
        headers=headers,
    )
    assert activate.status_code == 200
    assert "activated" in activate.json()["message"].lower()

    deactivate = client.post(
        "/api/v1/bot/kill-switch/deactivate",
        json={"reason": "test done", "actor": "pytest"},
        headers=headers,
    )
    assert deactivate.status_code == 200
    assert "deactivated" in deactivate.json()["message"].lower()


def test_auth_login_with_email_password_success(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    monkeypatch.setenv("AUTH_TOKEN_TTL_SECONDS", "1800")
    get_settings.cache_clear()

    login_email = f"dashboard.user.{uuid.uuid4().hex[:10]}@example.com"
    login_password = "Pass123."
    _create_dashboard_user(login_email, login_password)

    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/login",
            json={"email": login_email, "password": login_password},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["token_type"] == "bearer"
        assert payload["expires_in_seconds"] == 1800
        assert payload["access_token"]
    finally:
        get_settings.cache_clear()


def test_auth_login_invalid_password_rejected(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    get_settings.cache_clear()

    login_email = f"dashboard.user.{uuid.uuid4().hex[:10]}@example.com"
    login_password = "Pass123."
    _create_dashboard_user(login_email, login_password)

    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/login",
            json={"email": login_email, "password": "wrong-password"},
        )
        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()
    finally:
        get_settings.cache_clear()


def test_protected_route_requires_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    get_settings.cache_clear()

    try:
        client = TestClient(app)
        response = client.get("/api/v1/bot/status")
        assert response.status_code == 401
    finally:
        get_settings.cache_clear()


def test_logout_revokes_token_and_blocks_next_request(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    monkeypatch.setenv("AUTH_TOKEN_TTL_SECONDS", "1800")
    get_settings.cache_clear()

    login_email = f"dashboard.user.{uuid.uuid4().hex[:10]}@example.com"
    login_password = "Pass123."
    _create_dashboard_user(login_email, login_password)

    try:
        client = TestClient(app)
        headers = _login_and_get_auth_headers(client, login_email, login_password)

        logout_response = client.post("/api/v1/auth/logout", headers=headers)
        assert logout_response.status_code == 200
        assert "logged out" in logout_response.json()["message"].lower()

        denied_response = client.get("/api/v1/bot/status", headers=headers)
        assert denied_response.status_code == 401
    finally:
        get_settings.cache_clear()
