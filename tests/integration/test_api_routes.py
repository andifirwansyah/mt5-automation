from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from src.api.main import app
from src.config.settings import get_settings
from src.repositories.auth_repository import AuthRepository
from src.repositories.account_repository import AccountRepository
from src.repositories.market_repository import MarketRepository
from src.repositories.position_repository import PositionRepository
from src.repositories.safety_repository import SafetyRepository
from src.infrastructure.database.session import SessionLocal
from src.services.runtime_config_service import RuntimeConfigService
from src.services.password_hasher_service import hash_password


def test_fastapi_health_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"


def test_openapi_declares_bearer_auth_scheme() -> None:
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    payload = response.json()
    security_schemes = payload["components"]["securitySchemes"]
    assert "HTTPBearer" in security_schemes
    assert security_schemes["HTTPBearer"]["type"] == "http"
    assert security_schemes["HTTPBearer"]["scheme"] == "bearer"


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


def test_runtime_config_update_api(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    get_settings.cache_clear()

    login_email = f"dashboard.user.{uuid.uuid4().hex[:10]}@example.com"
    login_password = "Pass123."
    _create_dashboard_user(login_email, login_password)

    service = RuntimeConfigService(SessionLocal, get_settings(), cache_ttl_seconds=0.0)
    service.seed_defaults_if_missing(updated_by="pytest")
    original_limit = int(service.get_value("max_trades_per_day"))

    try:
        client = TestClient(app)
        headers = _login_and_get_auth_headers(client, login_email, login_password)

        update_response = client.put(
            "/api/v1/bot/runtime-configs/max_trades_per_day",
            json={"value": (original_limit + 2), "actor": "pytest", "reason": "api update test"},
            headers=headers,
        )
        assert update_response.status_code == 200
        updated_payload = update_response.json()["config"]
        assert updated_payload["config_key"] == "max_trades_per_day"
        assert updated_payload["config_value"] == (original_limit + 2)

        list_response = client.get("/api/v1/bot/runtime-configs", headers=headers)
        assert list_response.status_code == 200
        items = list_response.json()["items"]
        target_item = next(item for item in items if item["config_key"] == "max_trades_per_day")
        assert target_item["config_value"] == (original_limit + 2)
    finally:
        service.update_config(
            config_key="max_trades_per_day",
            config_value=original_limit,
            updated_by="pytest",
            update_reason="restore after api test",
        )
        get_settings.cache_clear()


def test_positions_websocket_streams_open_and_update_events(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    get_settings.cache_clear()

    login_email = f"dashboard.user.{uuid.uuid4().hex[:10]}@example.com"
    login_password = "Pass123."
    _create_dashboard_user(login_email, login_password)

    setup_session = SessionLocal()
    try:
        account_repo = AccountRepository(setup_session)
        market_repo = MarketRepository(setup_session)
        position_repo = PositionRepository(setup_session)
        account = account_repo.get_or_create_trading_account(
            account_number=f"acct-{uuid.uuid4().hex[:8]}",
            account_name="WS Test",
            broker_server="Demo",
            base_currency="USD",
            leverage=100,
            metadata={"source": "pytest"},
        )
        symbol = market_repo.get_or_create_symbol("XAUUSD")
        setup_session.commit()
    finally:
        setup_session.close()

    client = TestClient(app)
    headers = _login_and_get_auth_headers(client, login_email, login_password)
    token = headers["Authorization"].split(" ", 1)[1]

    with client.websocket_connect(f"/ws/v1/positions?access_token={token}") as websocket:
        first = websocket.receive_json()
        assert first["event"] == "positions.snapshot"
        assert first["payload"]["authenticated_user"] == login_email

        update_session = SessionLocal()
        try:
            position_repo = PositionRepository(update_session)
            created = position_repo.upsert_position(
                account_id=account.id,
                symbol_id=symbol.id,
                side="BUY",
                volume_lot=0.10,
                entry_price=2300.0,
                stop_loss=2295.0,
                take_profit=2310.0,
                status="OPEN",
                opened_at=datetime.now(timezone.utc),
                mt5_position_ticket=987654,
                profit=5.0,
                details={"price_current": 2301.0, "profit": 5.0},
            )
            position_repo.create_position_snapshot(
                position_id=created.id,
                snapshot_time=datetime.now(timezone.utc),
                current_price=2301.0,
                unrealized_profit=5.0,
                swap=0.0,
                commission=0.0,
                raw_payload={"source": "pytest"},
            )
            update_session.commit()
        finally:
            update_session.close()

        opened_event = websocket.receive_json()
        assert opened_event["event"] == "position.opened"
        assert opened_event["payload"]["mt5_position_ticket"] == 987654
        assert opened_event["payload"]["latest_snapshot"]["unrealized_profit"] == 5.0

        update_session = SessionLocal()
        try:
            position_repo = PositionRepository(update_session)
            updated = position_repo.upsert_position(
                account_id=account.id,
                symbol_id=symbol.id,
                side="BUY",
                volume_lot=0.10,
                entry_price=2300.0,
                stop_loss=2296.0,
                take_profit=2312.0,
                status="OPEN",
                opened_at=created.opened_at,
                mt5_position_ticket=987654,
                profit=9.5,
                details={"price_current": 2302.5, "profit": 9.5},
            )
            position_repo.create_position_snapshot(
                position_id=updated.id,
                snapshot_time=datetime.now(timezone.utc),
                current_price=2302.5,
                unrealized_profit=9.5,
                swap=0.0,
                commission=0.0,
                raw_payload={"source": "pytest-update"},
            )
            update_session.commit()
        finally:
            update_session.close()

        updated_event = websocket.receive_json()
        assert updated_event["event"] == "position.updated"
        assert updated_event["payload"]["stop_loss"] == 2296.0
        assert updated_event["payload"]["latest_snapshot"]["unrealized_profit"] == 9.5

        update_session = SessionLocal()
        try:
            position_repo = PositionRepository(update_session)
            position_repo.close_position(
                position_id=updated.id,
                close_price=2303.0,
                profit=11.0,
                closed_at=datetime.now(timezone.utc),
            )
            update_session.commit()
        finally:
            update_session.close()

        closed_event = websocket.receive_json()
        assert closed_event["event"] == "position.closed"
        assert closed_event["payload"]["status"] == "CLOSED"
        assert closed_event["payload"]["close_price"] == 2303.0


def test_kill_switch_websocket_streams_status_changes(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    get_settings.cache_clear()

    login_email = f"dashboard.user.{uuid.uuid4().hex[:10]}@example.com"
    login_password = "Pass123."
    _create_dashboard_user(login_email, login_password)

    cleanup_session = SessionLocal()
    try:
        repo = SafetyRepository(cleanup_session)
        repo.deactivate_kill_switch(deactivated_by="pytest-pre-clean", details={"reason": "pre-clean"})
        cleanup_session.commit()
    finally:
        cleanup_session.close()

    client = TestClient(app)
    headers = _login_and_get_auth_headers(client, login_email, login_password)
    token = headers["Authorization"].split(" ", 1)[1]

    with client.websocket_connect(f"/ws/v1/kill-switch?access_token={token}") as websocket:
        snapshot_event = websocket.receive_json()
        assert snapshot_event["event"] == "kill_switch.snapshot"
        assert snapshot_event["payload"]["authenticated_user"] == login_email
        assert snapshot_event["payload"]["is_active"] is False
        assert snapshot_event["payload"]["kill_switch"] is None

        activate_session = SessionLocal()
        try:
            repo = SafetyRepository(activate_session)
            repo.activate_kill_switch(
                reason="pytest activation",
                activated_by="pytest",
                activated_at=datetime.now(timezone.utc),
            )
            activate_session.commit()
        finally:
            activate_session.close()

        activated_event = websocket.receive_json()
        assert activated_event["event"] == "kill_switch.updated"
        assert activated_event["payload"]["is_active"] is True
        assert activated_event["payload"]["kill_switch"]["reason"] == "pytest activation"
        assert activated_event["payload"]["kill_switch"]["is_active"] is True

        deactivate_session = SessionLocal()
        try:
            repo = SafetyRepository(deactivate_session)
            repo.deactivate_kill_switch(
                deactivated_by="pytest",
                deactivated_at=datetime.now(timezone.utc),
                details={"reason": "pytest deactivate"},
            )
            deactivate_session.commit()
        finally:
            deactivate_session.close()

        deactivated_event = websocket.receive_json()
        assert deactivated_event["event"] == "kill_switch.updated"
        assert deactivated_event["payload"]["is_active"] is False
        assert deactivated_event["payload"]["kill_switch"]["is_active"] is False
        assert deactivated_event["payload"]["kill_switch"]["deactivated_by"] == "pytest"


def test_positions_websocket_closes_db_session_before_send(monkeypatch) -> None:
    from src.api.routes import ws_routes

    captured: dict[str, object] = {}

    class FakeSession:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    class FakePositionStreamService:
        def __init__(self, session: FakeSession) -> None:
            captured["session"] = session

        def load_open_positions(self) -> dict[str, dict]:
            return {"position-1": {"id": "position-1", "status": "OPEN"}}

        def diff_positions(self, previous_state: dict[str, dict], current_state: dict[str, dict]) -> list:
            return []

    class FakeWebSocket:
        query_params: dict[str, str] = {}
        headers: dict[str, str] = {}

        async def accept(self) -> None:
            return None

        async def send_json(self, payload: dict[str, object]) -> None:
            session = captured["session"]
            assert isinstance(session, FakeSession)
            assert session.closed is True
            assert payload["event"] == "positions.snapshot"
            raise WebSocketDisconnect()

    monkeypatch.setattr(ws_routes, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(ws_routes, "PositionStreamService", FakePositionStreamService)

    async def fake_authenticate_websocket(websocket: object) -> dict[str, str]:
        return {"email": "ops@example.com"}

    monkeypatch.setattr(ws_routes, "_authenticate_websocket", fake_authenticate_websocket)

    asyncio.run(ws_routes.stream_positions(FakeWebSocket()))


def test_positions_websocket_stops_on_client_disconnect_while_idle(monkeypatch) -> None:
    from src.api.routes import ws_routes

    class FakeSession:
        def close(self) -> None:
            return None

    class FakePositionStreamService:
        def __init__(self, session: FakeSession) -> None:
            self.session = session

        def load_open_positions(self) -> dict[str, dict]:
            return {}

        def diff_positions(self, previous_state: dict[str, dict], current_state: dict[str, dict]) -> list:
            return []

    class FakeWebSocket:
        query_params: dict[str, str] = {}
        headers: dict[str, str] = {}

        def __init__(self) -> None:
            self.sent_events: list[str] = []
            self.receive_calls = 0

        async def accept(self) -> None:
            return None

        async def send_json(self, payload: dict[str, object]) -> None:
            self.sent_events.append(str(payload["event"]))

        async def receive(self) -> dict[str, object]:
            self.receive_calls += 1
            return {"type": "websocket.disconnect", "code": 1000, "reason": "client closed"}

    websocket = FakeWebSocket()

    monkeypatch.setattr(ws_routes, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(ws_routes, "PositionStreamService", FakePositionStreamService)

    async def fake_authenticate_websocket(websocket: object) -> dict[str, str]:
        return {"email": "ops@example.com"}

    monkeypatch.setattr(ws_routes, "_authenticate_websocket", fake_authenticate_websocket)

    asyncio.run(ws_routes.stream_positions(websocket))

    assert websocket.sent_events == ["positions.snapshot"]
    assert websocket.receive_calls == 1


def test_kill_switch_websocket_normalizes_send_runtime_error_as_disconnect(monkeypatch) -> None:
    from src.api.routes import ws_routes

    class FakeSession:
        def close(self) -> None:
            return None

    class FakeStreamService:
        def __init__(self, repository: object) -> None:
            self.repository = repository

        def load_snapshot_status(self) -> dict[str, object | None]:
            return {"is_active": False, "kill_switch": None}

    class FakeWebSocket:
        query_params: dict[str, str] = {}
        headers: dict[str, str] = {}

        async def accept(self) -> None:
            return None

        async def send_json(self, payload: dict[str, object]) -> None:
            raise RuntimeError("Unexpected ASGI message 'websocket.send', after sending 'websocket.close' or response already completed.")

        async def receive(self) -> dict[str, object]:
            return {"type": "websocket.disconnect", "code": 1000}

    monkeypatch.setattr(ws_routes, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(ws_routes, "KillSwitchStreamService", FakeStreamService)
    monkeypatch.setattr(ws_routes, "SafetyRepository", lambda session: object())

    async def fake_authenticate_websocket(websocket: object) -> dict[str, str]:
        return {"email": "ops@example.com"}

    monkeypatch.setattr(ws_routes, "_authenticate_websocket", fake_authenticate_websocket)

    asyncio.run(ws_routes.stream_kill_switch_status(FakeWebSocket()))
