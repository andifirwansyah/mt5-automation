"""Performance and feedback endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.deps import get_db, paginate_query, pagination_params
from src.infrastructure.database.models import PerformanceByStrategy, PerformanceDaily, StrategyFeedbackEvent

router = APIRouter(prefix="/api/v1", tags=["performance"])


def _build_summary_payload(db: Session, *, trade_date: object | None = None) -> dict[str, float | int]:
    stmt = select(PerformanceDaily)
    if trade_date is not None:
        stmt = stmt.where(PerformanceDaily.trade_date == trade_date)

    subquery = stmt.subquery()

    total_trades = int(db.execute(select(func.coalesce(func.sum(subquery.c.total_trades), 0))).scalar_one())
    total_profit = float(db.execute(select(func.coalesce(func.sum(subquery.c.gross_profit), 0))).scalar_one())
    total_loss = abs(float(db.execute(select(func.coalesce(func.sum(subquery.c.gross_loss), 0))).scalar_one()))
    total_net_profit = float(db.execute(select(func.coalesce(func.sum(subquery.c.net_profit), 0))).scalar_one())
    weighted_win_rate_numerator = float(
        db.execute(select(func.coalesce(func.sum(subquery.c.win_rate * subquery.c.total_trades), 0.0))).scalar_one()
    )
    win_rate = (weighted_win_rate_numerator / total_trades) if total_trades > 0 else 0.0

    return {
        "total_trades": total_trades,
        "total_profit": total_profit,
        "total_loss": total_loss,
        "total_net_profit": total_net_profit,
        "win_rate": win_rate,
    }


@router.get("/performance/summary")
def get_performance_summary(db: Session = Depends(get_db)) -> dict:
    today_trade_date = datetime.now(timezone.utc).date()
    return {
        "overall": _build_summary_payload(db),
        "today": _build_summary_payload(db, trade_date=today_trade_date),
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
