import pytest
from sqlalchemy.orm import Session

from ai_trading_automation.config import AppSettings
from ai_trading_automation.core.database import (
    check_db_health,
    create_db_engine,
    create_session_factory,
    get_db_session,
)


def test_app_settings_load_mysql_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_NAME", "ai-trading-automation")
    monkeypatch.setenv("DB_CONNECTION", "mysql")
    monkeypatch.setenv(
        "DATABASE_URL",
        "mysql+pymysql://root:secret@127.0.0.1:3306/ai_trading_automation?charset=utf8mb4",
    )

    settings = AppSettings.from_env()

    assert settings.db_connection == "mysql"
    assert settings.database_url.startswith("mysql+pymysql://")
    assert settings.trade_journal_backend in {"file", "db"}
    assert settings.paper_execution_backend in {"memory", "db"}


def test_app_settings_reject_invalid_mysql_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_CONNECTION", "mysql")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")

    with pytest.raises(ValueError, match="Invalid DATABASE_URL for MySQL"):
        AppSettings.from_env()


def test_create_engine_session_and_healthcheck_sqlite() -> None:
    settings = AppSettings(
        app_env="test",
        app_name="ai-trading-automation",
        db_connection="sqlite",
        database_url="sqlite+pysqlite:///:memory:",
        trade_journal_backend="file",
        paper_execution_backend="memory",
        strict_db_runtime=False,
    )

    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)

    session_iter = get_db_session(session_factory)
    session = next(session_iter)
    assert isinstance(session, Session)
    session_iter.close()

    assert check_db_health(engine) is True
