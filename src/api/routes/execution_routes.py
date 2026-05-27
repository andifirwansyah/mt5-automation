"""Execution endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.deps import get_db, model_to_dict, paginate_query, pagination_params
from src.infrastructure.database.models import ExecutionDecision, ExecutionOrder

router = APIRouter(prefix="/api/v1/execution", tags=["execution"])


@router.get("/decisions")
def get_execution_decisions(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(ExecutionDecision).order_by(ExecutionDecision.created_at.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])


@router.get("/orders")
def get_execution_orders(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(ExecutionOrder).order_by(ExecutionOrder.created_at.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])


@router.get("/orders/{order_id}")
def get_execution_order(order_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    row = db.get(ExecutionOrder, order_id)
    return {"order": model_to_dict(row) if row else None}
