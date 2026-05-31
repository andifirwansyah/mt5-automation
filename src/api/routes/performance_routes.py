"""Performance and feedback endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.deps import get_db, paginate_query, pagination_params
from src.infrastructure.database.models import PerformanceByStrategy, PerformanceDaily, StrategyFeedbackEvent

router = APIRouter(prefix="/api/v1", tags=["performance"])


@router.get("/performance/summary")
def get_performance_summary(db: Session = Depends(get_db)) -> dict:
    total_trades = int(db.execute(select(func.coalesce(func.sum(PerformanceDaily.total_trades), 0))).scalar_one())
    total_net_profit = float(db.execute(select(func.coalesce(func.sum(PerformanceDaily.net_profit), 0))).scalar_one())
    avg_win_rate = float(db.execute(select(func.coalesce(func.avg(PerformanceDaily.win_rate), 0))).scalar_one())
    return {
        "total_trades": total_trades,
        "total_net_profit": total_net_profit,
        "average_win_rate": avg_win_rate,
    }


@router.get("/performance/daily")
def get_performance_daily(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(PerformanceDaily).order_by(PerformanceDaily.trade_date.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])


@router.get("/performance/by-strategy")
def get_performance_by_strategy(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(PerformanceByStrategy).order_by(PerformanceByStrategy.created_at.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])


@router.get("/feedback/strategy")
def get_strategy_feedback(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(StrategyFeedbackEvent).order_by(StrategyFeedbackEvent.created_at.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])
