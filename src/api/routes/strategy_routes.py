"""Strategy endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.deps import get_db, paginate_query, pagination_params
from src.infrastructure.database.models import PerformanceByStrategy, Strategy, StrategySelection

router = APIRouter(prefix="/api/v1/strategies", tags=["strategies"])


@router.get("")
def get_strategies(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(Strategy).order_by(Strategy.code.asc())
    return paginate_query(db, stmt, p["limit"], p["offset"])


@router.get("/selections")
def get_strategy_selections(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(StrategySelection).order_by(StrategySelection.created_at.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])


@router.get("/performance")
def get_strategy_performance(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(PerformanceByStrategy).order_by(PerformanceByStrategy.created_at.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])
