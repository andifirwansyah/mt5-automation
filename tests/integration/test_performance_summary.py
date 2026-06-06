from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from src.api.main import app
from src.config.settings import get_settings
from src.repositories.account_repository import AccountRepository
from src.repositories.auth_repository import AuthRepository
from src.repositories.execution_repository import ExecutionRepository
from src.repositories.market_repository import MarketRepository
from src.repositories.position_repository import PositionRepository
from src.infrastructure.database.models import PerformanceByStrategy, PerformanceDaily, Strategy
from src.infrastructure.database.session import SessionLocal
from src.repositories.performance_repository import PerformanceRepository
from src.repositories.signal_repository import SignalRepository
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
    assert payload["overall"]["total_trades"] >= 1
    assert payload["overall"]["total_profit"] >= 25.0
    assert payload["overall"]["total_net_profit"] >= 25.0
    assert payload["overall"]["total_loss"] >= 0.0
    assert payload["today"]["total_trades"] >= 1
    assert payload["today"]["total_profit"] >= 25.0


def test_performance_summary_reads_precomputed_performance(monkeypatch) -> None:
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

        analyzer = PerformanceAnalyzer(PerformanceRepository(session))
        result = analyzer.run_cycle(reference_time=now)
        assert result["total_trades"] >= 1
        assert result["net_profit"] >= 40.0
    finally:
        session.close()

    client = TestClient(app)
    headers = _login_and_get_auth_headers(client, login_email, login_password)

    summary_response = client.get("/api/v1/performance/summary", headers=headers)
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()
    assert summary_payload["overall"]["total_trades"] >= 1
    assert summary_payload["overall"]["total_profit"] >= 40.0
    assert summary_payload["overall"]["total_net_profit"] >= 40.0
    assert summary_payload["today"]["total_trades"] >= 1


def test_performance_recalculate_endpoint_is_not_available(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    get_settings.cache_clear()

    login_email = f"dashboard.user.{uuid.uuid4().hex[:10]}@example.com"
    login_password = "Pass123."
    _create_dashboard_user(login_email, login_password)

    client = TestClient(app)
    headers = _login_and_get_auth_headers(client, login_email, login_password)

    response = client.post("/api/v1/performance/recalculate", headers=headers)

    assert response.status_code == 404


def test_performance_recalculate_backfills_profit_from_position_details(monkeypatch) -> None:
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
            account_name="Perf Detail Profit Test",
            broker_server="Demo",
            base_currency="USD",
            leverage=100,
            metadata={"source": "pytest"},
        )
        symbol = market_repo.get_or_create_symbol("XAUUSD")
        position = position_repo.upsert_position(
            account_id=account.id,
            symbol_id=symbol.id,
            side="BUY",
            volume_lot=0.01,
            entry_price=2300.0,
            stop_loss=2295.0,
            take_profit=2310.0,
            close_price=2300.0,
            profit=0.0,
            status="CLOSED",
            opened_at=now - timedelta(minutes=30),
            closed_at=now - timedelta(minutes=5),
            mt5_position_ticket=999100,
            details={"price_current": 2306.0, "profit": 18.5, "source": "pytest-detail-profit"},
        )
        session.commit()

        analyzer = PerformanceAnalyzer(PerformanceRepository(session))
        result = analyzer.run_cycle(reference_time=now)
        session.refresh(position)

        assert result["total_trades"] >= 1
        assert result["net_profit"] >= 18.5
        assert float(position.profit or 0.0) == 18.5
        assert float(position.close_price or 0.0) == 2306.0
    finally:
        session.close()

    client = TestClient(app)
    headers = _login_and_get_auth_headers(client, login_email, login_password)
    summary_response = client.get("/api/v1/performance/summary", headers=headers)
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()
    assert summary_payload["overall"]["total_trades"] >= 1
    assert summary_payload["overall"]["total_profit"] >= 18.5
    assert summary_payload["overall"]["total_net_profit"] >= 18.5
    assert summary_payload["today"]["total_profit"] >= 18.5


def test_performance_recalculate_backfills_prior_day_loss_and_summary_total_loss(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    get_settings.cache_clear()

    now = datetime.now(timezone.utc).replace(microsecond=0)
    previous_day = now - timedelta(days=1)
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
            account_name="Perf Prior Day Loss Test",
            broker_server="Demo",
            base_currency="USD",
            leverage=100,
            metadata={"source": "pytest"},
        )
        symbol = market_repo.get_or_create_symbol("XAUUSD")
        position = position_repo.upsert_position(
            account_id=account.id,
            symbol_id=symbol.id,
            side="SELL",
            volume_lot=0.01,
            entry_price=4470.92,
            stop_loss=4477.74,
            take_profit=4457.63,
            close_price=4470.92,
            profit=0.0,
            status="CLOSED",
            opened_at=previous_day - timedelta(hours=2),
            closed_at=previous_day,
            mt5_position_ticket=999103,
            details={"price_current": 4477.5, "profit": -6.58, "source": "pytest-prior-day-loss"},
        )
        session.commit()

        analyzer = PerformanceAnalyzer(PerformanceRepository(session))
        result = analyzer.run_cycle(reference_time=now)
        session.refresh(position)

        assert result["total_trades"] >= 0
        assert float(position.profit or 0.0) == -6.58
        assert float(position.close_price or 0.0) == 4477.5
    finally:
        session.close()

    client = TestClient(app)
    headers = _login_and_get_auth_headers(client, login_email, login_password)
    summary_response = client.get("/api/v1/performance/summary", headers=headers)
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()
    assert summary_payload["overall"]["total_trades"] >= 1
    assert summary_payload["overall"]["total_loss"] >= 6.58
    assert summary_payload["today"]["total_loss"] >= 0.0


def test_performance_analyzer_backfills_prior_day_strategy_performance(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    get_settings.cache_clear()

    now = datetime.now(timezone.utc).replace(microsecond=0)
    previous_day = now - timedelta(days=1)
    login_email = f"dashboard.user.{uuid.uuid4().hex[:10]}@example.com"
    login_password = "Pass123."
    _create_dashboard_user(login_email, login_password)

    session = SessionLocal()
    try:
        account_repo = AccountRepository(session)
        market_repo = MarketRepository(session)
        position_repo = PositionRepository(session)
        signal_repo = SignalRepository(session)
        execution_repo = ExecutionRepository(session)

        account = account_repo.get_or_create_trading_account(
            account_number=f"acct-{uuid.uuid4().hex[:8]}",
            account_name="Strategy Perf Prior Day Test",
            broker_server="Demo",
            base_currency="USD",
            leverage=100,
            metadata={"source": "pytest"},
        )
        symbol = market_repo.get_or_create_symbol("XAUUSD")
        timeframe = market_repo.get_or_create_timeframe("M5", minutes=5)
        strategy = Strategy(
            code=f"PERF_TEST_{uuid.uuid4().hex[:8]}",
            name="Performance Backfill Test Strategy",
            description="pytest strategy performance backfill",
            is_active=True,
            metadata_json={"source": "pytest"},
        )
        session.add(strategy)
        session.flush()
        strategy_id = strategy.id

        signal = signal_repo.create_signal(
            trace_id=uuid.uuid4(),
            symbol_id=symbol.id,
            timeframe_id=timeframe.id,
            strategy_id=strategy.id,
            direction="BUY",
            status="APPROVED",
            signal_time=previous_day - timedelta(minutes=30),
            entry_price=2300.0,
            stop_loss=2295.0,
            take_profit=2310.0,
            lot_size=0.01,
            confidence=0.75,
            features={"source": "pytest"},
        )
        order = execution_repo.create_execution_order(
            signal_id=signal.id,
            symbol_id=symbol.id,
            side="BUY",
            order_type="MARKET",
            volume_lot=0.01,
            requested_price=2300.0,
            stop_loss=2295.0,
            take_profit=2310.0,
            deviation=20,
            status="FILLED",
            executed_at=previous_day - timedelta(minutes=25),
        )
        position_repo.upsert_position(
            account_id=account.id,
            symbol_id=symbol.id,
            side="BUY",
            volume_lot=0.01,
            entry_price=2300.0,
            stop_loss=2295.0,
            take_profit=2310.0,
            close_price=2308.0,
            profit=8.0,
            status="CLOSED",
            opened_at=previous_day - timedelta(minutes=25),
            closed_at=previous_day - timedelta(minutes=5),
            execution_order_id=order.id,
            mt5_position_ticket=999104,
            details={"source": "pytest-strategy-prior-day"},
        )
        session.commit()

        analyzer = PerformanceAnalyzer(PerformanceRepository(session))
        analyzer.run_cycle(reference_time=now)

        row = session.execute(
            select(PerformanceByStrategy).where(PerformanceByStrategy.strategy_id == strategy_id)
        ).scalar_one_or_none()
        assert row is not None
        assert row.period_start == previous_day.date()
        assert row.period_end == previous_day.date()
        assert row.total_trades == 1
        assert float(row.net_profit) == 8.0
    finally:
        session.close()

    client = TestClient(app)
    headers = _login_and_get_auth_headers(client, login_email, login_password)
    response = client.get("/api/v1/strategies/performance", headers=headers)
    assert response.status_code == 200
    assert strategy_id is not None
    matching_items = [item for item in response.json()["items"] if item["strategy_id"] == str(strategy_id)]
    assert matching_items


def test_performance_summary_uses_weighted_average_win_rate(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    get_settings.cache_clear()

    now = datetime.now(timezone.utc).replace(microsecond=0)
    login_email = f"dashboard.user.{uuid.uuid4().hex[:10]}@example.com"
    login_password = "Pass123."
    _create_dashboard_user(login_email, login_password)

    expected_weighted_win_rate = 0.0
    simple_average_win_rate = 0.0

    session = SessionLocal()
    try:
        account_repo = AccountRepository(session)
        market_repo = MarketRepository(session)
        position_repo = PositionRepository(session)

        account_a = account_repo.get_or_create_trading_account(
            account_number=f"acct-{uuid.uuid4().hex[:8]}",
            account_name="Weighted Win Rate A",
            broker_server="Demo",
            base_currency="USD",
            leverage=100,
            metadata={"source": "pytest"},
        )
        account_b = account_repo.get_or_create_trading_account(
            account_number=f"acct-{uuid.uuid4().hex[:8]}",
            account_name="Weighted Win Rate B",
            broker_server="Demo",
            base_currency="USD",
            leverage=100,
            metadata={"source": "pytest"},
        )
        symbol = market_repo.get_or_create_symbol("XAUUSD")

        position_repo.upsert_position(
            account_id=account_a.id,
            symbol_id=symbol.id,
            side="BUY",
            volume_lot=0.01,
            entry_price=2300.0,
            stop_loss=2295.0,
            take_profit=2310.0,
            close_price=2305.0,
            profit=5.0,
            status="CLOSED",
            opened_at=now - timedelta(minutes=40),
            closed_at=now - timedelta(minutes=30),
            mt5_position_ticket=999201,
            details={"source": "pytest-weighted-a-1"},
        )
        position_repo.upsert_position(
            account_id=account_b.id,
            symbol_id=symbol.id,
            side="BUY",
            volume_lot=0.01,
            entry_price=2301.0,
            stop_loss=2296.0,
            take_profit=2311.0,
            close_price=2306.0,
            profit=5.0,
            status="CLOSED",
            opened_at=now - timedelta(minutes=29),
            closed_at=now - timedelta(minutes=20),
            mt5_position_ticket=999202,
            details={"source": "pytest-weighted-b-1"},
        )
        position_repo.upsert_position(
            account_id=account_b.id,
            symbol_id=symbol.id,
            side="BUY",
            volume_lot=0.01,
            entry_price=2302.0,
            stop_loss=2297.0,
            take_profit=2312.0,
            close_price=2307.0,
            profit=5.0,
            status="CLOSED",
            opened_at=now - timedelta(minutes=19),
            closed_at=now - timedelta(minutes=10),
            mt5_position_ticket=999203,
            details={"source": "pytest-weighted-b-2"},
        )
        position_repo.upsert_position(
            account_id=account_b.id,
            symbol_id=symbol.id,
            side="SELL",
            volume_lot=0.01,
            entry_price=2303.0,
            stop_loss=2308.0,
            take_profit=2293.0,
            close_price=2308.0,
            profit=-5.0,
            status="CLOSED",
            opened_at=now - timedelta(minutes=9),
            closed_at=now - timedelta(minutes=5),
            mt5_position_ticket=999204,
            details={"source": "pytest-weighted-b-3"},
        )
        session.commit()

        analyzer = PerformanceAnalyzer(PerformanceRepository(session))
        result = analyzer.run_cycle(reference_time=now)
        assert result["total_trades"] >= 4

        total_trades = int(session.execute(select(func.coalesce(func.sum(PerformanceDaily.total_trades), 0))).scalar_one())
        weighted_numerator = float(
            session.execute(
                select(func.coalesce(func.sum(PerformanceDaily.win_rate * PerformanceDaily.total_trades), 0.0))
            ).scalar_one()
        )
        simple_average_win_rate = float(
            session.execute(select(func.coalesce(func.avg(PerformanceDaily.win_rate), 0.0))).scalar_one()
        )
        expected_weighted_win_rate = (weighted_numerator / total_trades) if total_trades > 0 else 0.0
    finally:
        session.close()

    client = TestClient(app)
    headers = _login_and_get_auth_headers(client, login_email, login_password)
    summary_response = client.get("/api/v1/performance/summary", headers=headers)
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()
    assert summary_payload["overall"]["total_trades"] >= 4
    assert summary_payload["overall"]["win_rate"] == expected_weighted_win_rate
    assert summary_payload["overall"]["win_rate"] != simple_average_win_rate


def test_performance_summary_exposes_overall_and_today_metrics(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    get_settings.cache_clear()

    now = datetime.now(timezone.utc).replace(microsecond=0)
    previous_day = now - timedelta(days=1)
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
            account_name="Perf Dashboard Summary Test",
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
            volume_lot=0.01,
            entry_price=2300.0,
            stop_loss=2295.0,
            take_profit=2310.0,
            close_price=2306.0,
            profit=6.0,
            status="CLOSED",
            opened_at=now - timedelta(minutes=35),
            closed_at=now - timedelta(minutes=30),
            mt5_position_ticket=999301,
            details={"source": "pytest-dashboard-today-win"},
        )
        position_repo.upsert_position(
            account_id=account.id,
            symbol_id=symbol.id,
            side="SELL",
            volume_lot=0.01,
            entry_price=2308.0,
            stop_loss=2313.0,
            take_profit=2298.0,
            close_price=2312.0,
            profit=-4.0,
            status="CLOSED",
            opened_at=now - timedelta(minutes=20),
            closed_at=now - timedelta(minutes=10),
            mt5_position_ticket=999302,
            details={"source": "pytest-dashboard-today-loss"},
        )
        position_repo.upsert_position(
            account_id=account.id,
            symbol_id=symbol.id,
            side="BUY",
            volume_lot=0.01,
            entry_price=2290.0,
            stop_loss=2285.0,
            take_profit=2300.0,
            close_price=2295.0,
            profit=5.0,
            status="CLOSED",
            opened_at=previous_day - timedelta(minutes=40),
            closed_at=previous_day - timedelta(minutes=30),
            mt5_position_ticket=999303,
            details={"source": "pytest-dashboard-overall-prior"},
        )
        session.commit()

        analyzer = PerformanceAnalyzer(PerformanceRepository(session))
        analyzer.run_cycle(reference_time=now)
    finally:
        session.close()

    client = TestClient(app)
    headers = _login_and_get_auth_headers(client, login_email, login_password)
    summary_response = client.get("/api/v1/performance/summary", headers=headers)
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()

    assert set(summary_payload.keys()) == {"overall", "today"}
    assert summary_payload["overall"]["total_trades"] >= 3
    assert summary_payload["overall"]["total_profit"] >= 11.0
    assert summary_payload["overall"]["total_loss"] >= 4.0
    assert summary_payload["overall"]["total_net_profit"] >= 7.0
    assert summary_payload["overall"]["win_rate"] >= 0.0

    assert summary_payload["today"]["total_trades"] >= 2
    assert summary_payload["today"]["total_profit"] >= 6.0
    assert summary_payload["today"]["total_loss"] >= 4.0
    assert summary_payload["today"]["total_net_profit"] >= 2.0
    assert summary_payload["today"]["win_rate"] >= 0.0


def test_performance_chart_supports_date_range_filters(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    get_settings.cache_clear()

    now = datetime.now(timezone.utc).replace(microsecond=0)
    previous_day = now - timedelta(days=1)
    two_days_ago = now - timedelta(days=2)
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
            account_name="Perf Chart Filter Test",
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
            volume_lot=0.01,
            entry_price=2300.0,
            stop_loss=2295.0,
            take_profit=2310.0,
            close_price=2304.0,
            profit=4.0,
            status="CLOSED",
            opened_at=two_days_ago - timedelta(minutes=20),
            closed_at=two_days_ago,
            mt5_position_ticket=999401,
            details={"source": "pytest-chart-day-1"},
        )
        position_repo.upsert_position(
            account_id=account.id,
            symbol_id=symbol.id,
            side="SELL",
            volume_lot=0.01,
            entry_price=2310.0,
            stop_loss=2315.0,
            take_profit=2300.0,
            close_price=2307.0,
            profit=3.0,
            status="CLOSED",
            opened_at=previous_day - timedelta(minutes=20),
            closed_at=previous_day,
            mt5_position_ticket=999402,
            details={"source": "pytest-chart-day-2"},
        )
        position_repo.upsert_position(
            account_id=account.id,
            symbol_id=symbol.id,
            side="BUY",
            volume_lot=0.01,
            entry_price=2320.0,
            stop_loss=2315.0,
            take_profit=2330.0,
            close_price=2318.0,
            profit=-2.0,
            status="CLOSED",
            opened_at=now - timedelta(minutes=20),
            closed_at=now,
            mt5_position_ticket=999403,
            details={"source": "pytest-chart-day-3"},
        )
        session.commit()

        analyzer = PerformanceAnalyzer(PerformanceRepository(session))
        analyzer.run_cycle(reference_time=now)
    finally:
        session.close()

    client = TestClient(app)
    headers = _login_and_get_auth_headers(client, login_email, login_password)
    start_date = previous_day.date().isoformat()
    end_date = now.date().isoformat()

    response = client.get(
        f"/api/v1/performance/chart?start_date={start_date}&end_date={end_date}",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["start_date"] == start_date
    assert payload["summary"]["end_date"] == end_date
    assert payload["summary"]["points"] == 2
    assert payload["summary"]["total_trades"] >= 2
    assert len(payload["items"]) == 2
    assert set(payload["series"].keys()) == {
        "equity_curve",
        "daily_pnl",
        "gross_profit",
        "gross_loss",
        "trade_count",
        "drawdown",
        "win_rate",
    }
    assert payload["items"][0]["trade_date"] == start_date
    assert payload["items"][1]["trade_date"] == end_date
    assert payload["items"][1]["cumulative_net_profit"] == payload["summary"]["total_net_profit"]
    assert payload["series"]["equity_curve"][0]["x"] == start_date
    assert payload["series"]["equity_curve"][0]["y"] == payload["items"][0]["cumulative_net_profit"]
    assert payload["series"]["daily_pnl"][1]["y"] == payload["items"][1]["net_profit"]


def test_performance_chart_supports_group_by_week_and_month(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-secret-key")
    get_settings.cache_clear()

    now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
    day_a = now - timedelta(days=10)
    day_b = now - timedelta(days=8)
    day_c = now - timedelta(days=2)
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
            account_name="Perf Chart Group Test",
            broker_server="Demo",
            base_currency="USD",
            leverage=100,
            metadata={"source": "pytest"},
        )
        symbol = market_repo.get_or_create_symbol("XAUUSD")

        for ticket, trade_day, profit in [
            (999501, day_a, 5.0),
            (999502, day_b, -2.0),
            (999503, day_c, 7.0),
        ]:
            position_repo.upsert_position(
                account_id=account.id,
                symbol_id=symbol.id,
                side="BUY",
                volume_lot=0.01,
                entry_price=2300.0,
                stop_loss=2295.0,
                take_profit=2310.0,
                close_price=2300.0 + profit,
                profit=profit,
                status="CLOSED",
                opened_at=trade_day - timedelta(minutes=20),
                closed_at=trade_day,
                mt5_position_ticket=ticket,
                details={"source": "pytest-chart-group"},
            )
        session.commit()

        analyzer = PerformanceAnalyzer(PerformanceRepository(session))
        analyzer.run_cycle(reference_time=now)
    finally:
        session.close()

    client = TestClient(app)
    headers = _login_and_get_auth_headers(client, login_email, login_password)
    start_date = (now - timedelta(days=14)).date().isoformat()
    end_date = now.date().isoformat()

    week_response = client.get(
        f"/api/v1/performance/chart?start_date={start_date}&end_date={end_date}&group_by=week",
        headers=headers,
    )
    assert week_response.status_code == 200
    week_payload = week_response.json()
    assert week_payload["summary"]["group_by"] == "week"
    assert len(week_payload["items"]) == 2
    assert week_payload["items"][0]["period_start"] != week_payload["items"][1]["period_start"]
    assert week_payload["items"][1]["cumulative_net_profit"] == week_payload["summary"]["total_net_profit"]

    month_response = client.get(
        f"/api/v1/performance/chart?start_date={start_date}&end_date={end_date}&group_by=month",
        headers=headers,
    )
    assert month_response.status_code == 200
    month_payload = month_response.json()
    assert month_payload["summary"]["group_by"] == "month"
    assert len(month_payload["items"]) == 1
    assert month_payload["items"][0]["period_start"] == "2026-06-01"
    assert month_payload["items"][0]["total_trades"] >= 3


def test_close_position_uses_detail_profit_when_input_profit_zero() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)

    session = SessionLocal()
    try:
        account_repo = AccountRepository(session)
        market_repo = MarketRepository(session)
        position_repo = PositionRepository(session)

        account = account_repo.get_or_create_trading_account(
            account_number=f"acct-{uuid.uuid4().hex[:8]}",
            account_name="Close Position Detail Profit Test",
            broker_server="Demo",
            base_currency="USD",
            leverage=100,
            metadata={"source": "pytest"},
        )
        symbol = market_repo.get_or_create_symbol("XAUUSD")
        position = position_repo.upsert_position(
            account_id=account.id,
            symbol_id=symbol.id,
            side="BUY",
            volume_lot=0.01,
            entry_price=2300.0,
            stop_loss=2295.0,
            take_profit=2310.0,
            status="OPEN",
            opened_at=now - timedelta(minutes=15),
            mt5_position_ticket=999101,
            profit=0.0,
            details={"price_current": 2304.5, "profit": 12.25, "source": "pytest-close-fallback"},
        )
        session.commit()

        closed = position_repo.close_position(
            position_id=position.id,
            close_price=2300.0,
            profit=0.0,
            closed_at=now,
        )
        session.commit()
        assert closed is not None

        session.refresh(position)
        assert float(position.profit or 0.0) == 12.25
        assert float(position.close_price or 0.0) == 2304.5
    finally:
        session.close()


def test_close_position_preserves_breakeven_close_when_detail_profit_zero() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)

    session = SessionLocal()
    try:
        account_repo = AccountRepository(session)
        market_repo = MarketRepository(session)
        position_repo = PositionRepository(session)

        account = account_repo.get_or_create_trading_account(
            account_number=f"acct-{uuid.uuid4().hex[:8]}",
            account_name="Close Position Breakeven Test",
            broker_server="Demo",
            base_currency="USD",
            leverage=100,
            metadata={"source": "pytest"},
        )
        symbol = market_repo.get_or_create_symbol("XAUUSD")
        position = position_repo.upsert_position(
            account_id=account.id,
            symbol_id=symbol.id,
            side="BUY",
            volume_lot=0.01,
            entry_price=2300.0,
            stop_loss=2295.0,
            take_profit=2310.0,
            status="OPEN",
            opened_at=now - timedelta(minutes=15),
            mt5_position_ticket=999102,
            profit=0.0,
            details={"price_current": 2304.5, "profit": 0.0, "source": "pytest-breakeven"},
        )
        session.commit()

        closed = position_repo.close_position(
            position_id=position.id,
            close_price=2300.0,
            profit=0.0,
            closed_at=now,
        )
        session.commit()
        assert closed is not None

        session.refresh(position)
        assert float(position.profit or 0.0) == 0.0
        assert float(position.close_price or 0.0) == 2300.0
    finally:
        session.close()
