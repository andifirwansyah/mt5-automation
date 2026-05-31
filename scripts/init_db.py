"""Initialize and test PostgreSQL connection for AI Trading Automation."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.infrastructure.database.base import Base, TRADING_SCHEMA
from src.infrastructure.database.session import engine


def initialize_database() -> None:
    """Verify connection, ensure schema exists, and create initial tables."""

    try:
        with engine.begin() as connection:
            connection.execute(text("SELECT 1"))
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {TRADING_SCHEMA}"))

        Base.metadata.create_all(bind=engine)
        print("Database connection successful. Schema and tables are ready.")
    except SQLAlchemyError as exc:
        print(f"Database initialization failed: {exc}")
        raise


if __name__ == "__main__":
    initialize_database()
