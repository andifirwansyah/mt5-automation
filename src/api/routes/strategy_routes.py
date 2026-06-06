"""Strategy endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.deps import get_db, model_to_dict, paginate_query, pagination_params
from src.infrastructure.database.models import PerformanceByStrategy, Strategy, StrategyConfig, StrategySelection
from src.repositories.strategy_repository import StrategyRepository
from src.schemas import StrategyConfigUpdatePayload

router = APIRouter(prefix="/api/v1/strategies", tags=["strategies"])


@router.get("")
def get_strategies(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(Strategy).order_by(Strategy.code.asc())
    return paginate_query(db, stmt, p["limit"], p["offset"])


@router.get("/configs")
def get_strategy_configs(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(StrategyConfig).order_by(StrategyConfig.updated_at.desc(), StrategyConfig.created_at.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])


@router.put("/configs/{config_id}")
def update_strategy_config(config_id: uuid.UUID, payload: StrategyConfigUpdatePayload, db: Session = Depends(get_db)) -> dict:
    repo = StrategyRepository(db)
    updated = repo.update_strategy_config(
        config_id=config_id,
        config=payload.config,
        is_active=payload.is_active,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy config not found")
    db.commit()
    db.refresh(updated)
    return {"config": model_to_dict(updated)}


@router.get("/selections")
def get_strategy_selections(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(StrategySelection).order_by(StrategySelection.created_at.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])


@router.get("/performance")
def get_strategy_performance(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(PerformanceByStrategy).order_by(PerformanceByStrategy.created_at.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])
