"""Session management utilities for SQLAlchemy and FastAPI."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session, sessionmaker

from src.infrastructure.database.db import get_engine


engine = get_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency to provide a database session."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
