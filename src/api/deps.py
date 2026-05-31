"""Shared dependencies and helpers for API routes."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from src.infrastructure.database.session import get_db


def pagination_params(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, int]:
    return {"limit": limit, "offset": offset}


def serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: serialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [serialize_value(v) for v in value]
    return value


def model_to_dict(model: Any) -> dict[str, Any]:
    if hasattr(model, "__table__"):
        columns = [attr.key for attr in model.__mapper__.column_attrs]
        return {col: serialize_value(getattr(model, col)) for col in columns}
    if isinstance(model, dict):
        return {k: serialize_value(v) for k, v in model.items()}
    return {"value": serialize_value(model)}


def paginate_query(db: Session, stmt: Select[Any], limit: int, offset: int) -> dict[str, Any]:
    items = db.execute(stmt.limit(limit).offset(offset)).scalars().all()
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    return {
        "items": [model_to_dict(i) for i in items],
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


__all__ = [
    "get_db",
    "pagination_params",
    "model_to_dict",
    "paginate_query",
]
