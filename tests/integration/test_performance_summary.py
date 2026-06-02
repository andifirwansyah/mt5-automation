from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from src.api.main import app
from src.config.settings import get_settings
from src.repositories.account_repository import AccountRepository
from src.repositories.auth_repository import AuthRepository
from src.repositories.market_repository import MarketRepository
from src.repositories.position_repository import PositionRepository
from src.infrastructure.database.session import SessionLocal
from src.repositories.performance_repository import PerformanceRepository
from src.engines.performance_analyzer import PerformanceAnalyzer
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


def test_performance_summary_counts_closed_positions_without_execution_order(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    get_settings.cache_clear()

    now = datetime.now(timezone.utc).replace(microsecond=0)
    login_email = f"dashboard.user.{uuid.uuid4().hex[:10]}@example.com"
    login_password = "Pass123."
    _create_dashboard_user(login_email, login_password)

    session = SessionLocal()
    try:
        account_repo = AccountRepository(session)
        market_repo = MarketRepository(session)
        position_repo = PositionRepository(session)

        account = account_repo.get_or_create_trading_account(
            account_number=f"acct-{uuid.uuid4().hex[:8]}",
            account_name="Perf Test",
            broker_server="Demo",
            base_currency="USD",
            leverage=100,
            metadata={"source": "pytest"},
        )
        symbol = market_repo.get_or_create_symbol("XAUUSD")
        position_repo.upsert_position(
            account_id=account.id,
            symbol_id=symbol.id,
            side="BUY",
            volume_lot=0.10,
            entry_price=2300.0,
            stop_loss=2295.0,
            take_profit=2310.0,
            close_price=2304.0,
            profit=25.0,
            status="CLOSED",
            opened_at=now - timedelta(minutes=30),
            closed_at=now - timedelta(minutes=5),
            mt5_position_ticket=999001,
            details={"source": "pytest"},
        )
        session.commit()

        analyzer = PerformanceAnalyzer(PerformanceRepository(session))
        result = analyzer.run_cycle(reference_time=now)
        assert result["total_trades"] >= 1
        assert result["net_profit"] >= 25.0
    finally:
        session.close()

    client = TestClient(app)
    headers = _login_and_get_auth_headers(client, login_email, login_password)
    response = client.get("/api/v1/performance/summary", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_trades"] >= 1
    assert payload["total_net_profit"] >= 25.0


def test_performance_recalculate_endpoint_populates_summary(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    get_settings.cache_clear()

    now = datetime.now(timezone.utc).replace(microsecond=0)
    login_email = f"dashboard.user.{uuid.uuid4().hex[:10]}@example.com"
    login_password = "Pass123."
    _create_dashboard_user(login_email, login_password)

    session = SessionLocal()
    try:
        account_repo = AccountRepository(session)
        market_repo = MarketRepository(session)
        position_repo = PositionRepository(session)

        account = account_repo.get_or_create_trading_account(
            account_number=f"acct-{uuid.uuid4().hex[:8]}",
            account_name="Perf Recalc Test",
            broker_server="Demo",
            base_currency="USD",
            leverage=100,
            metadata={"source": "pytest"},
        )
        symbol = market_repo.get_or_create_symbol("XAUUSD")
        position_repo.upsert_position(
            account_id=account.id,
            symbol_id=symbol.id,
            side="SELL",
            volume_lot=0.20,
            entry_price=2310.0,
            stop_loss=2315.0,
            take_profit=2300.0,
            close_price=2302.0,
            profit=40.0,
            status="CLOSED",
            opened_at=now - timedelta(minutes=20),
            closed_at=now - timedelta(minutes=2),
            mt5_position_ticket=999002,
            details={"source": "pytest-recalc"},
        )
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    headers = _login_and_get_auth_headers(client, login_email, login_password)

    recalc_response = client.post("/api/v1/performance/recalculate", headers=headers)
    assert recalc_response.status_code == 200
    recalc_payload = recalc_response.json()
    assert recalc_payload["message"] == "Performance recalculated"
    assert recalc_payload["result"]["total_trades"] >= 1
    assert recalc_payload["result"]["net_profit"] >= 40.0

    summary_response = client.get("/api/v1/performance/summary", headers=headers)
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()
    assert summary_payload["total_trades"] >= 1
    assert summary_payload["total_net_profit"] >= 40.0
