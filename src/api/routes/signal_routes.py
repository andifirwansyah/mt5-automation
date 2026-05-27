"""Signal endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.deps import get_db, model_to_dict, paginate_query, pagination_params
from src.infrastructure.database.models import Signal

router = APIRouter(prefix="/api/v1/signals", tags=["signals"])


@router.get("/latest")
def get_latest_signal(db: Session = Depends(get_db)) -> dict:
    signal = db.execute(select(Signal).order_by(Signal.signal_time.desc()).limit(1)).scalar_one_or_none()
    return {"signal": model_to_dict(signal) if signal else None}


@router.get("")
def get_signals(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(Signal).order_by(Signal.signal_time.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])


@router.get("/{signal_id}")
def get_signal_by_id(signal_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    signal = db.get(Signal, signal_id)
    return {"signal": model_to_dict(signal) if signal else None}
