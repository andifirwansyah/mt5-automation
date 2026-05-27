"""Journal endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.deps import get_db, model_to_dict, paginate_query, pagination_params
from src.infrastructure.database.models import TradeJournal

router = APIRouter(prefix="/api/v1/journals", tags=["journals"])


@router.get("")
def get_journals(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(TradeJournal).order_by(TradeJournal.created_at.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])


@router.get("/{journal_id}")
def get_journal(journal_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    row = db.get(TradeJournal, journal_id)
    return {"journal": model_to_dict(row) if row else None}
