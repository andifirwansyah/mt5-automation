"""Database foundation utilities (engine/session/healthcheck)."""

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ai_trading_automation.config import AppSettings


def create_db_engine(settings: AppSettings) -> Engine:
    """Create SQLAlchemy engine from validated app settings."""
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create session factory for dependency injection or repositories."""
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def get_db_session(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    """Yield one DB session with safe close semantics."""
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def check_db_health(engine: Engine) -> bool:
    """Run lightweight health check query."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True
