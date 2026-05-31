"""Position endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.deps import get_db, paginate_query, pagination_params
from src.infrastructure.database.models import Position, PositionSnapshot

router = APIRouter(prefix="/api/v1/positions", tags=["positions"])


@router.get("/open")
def get_open_positions(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(Position).where(Position.status == "OPEN").order_by(Position.opened_at.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])


@router.get("/history")
def get_position_history(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(Position).order_by(Position.opened_at.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])


@router.get("/{position_id}/snapshots")
def get_position_snapshots(position_id: uuid.UUID, p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(PositionSnapshot).where(PositionSnapshot.position_id == position_id).order_by(PositionSnapshot.snapshot_time.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])
