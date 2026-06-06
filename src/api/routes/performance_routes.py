"""Performance and feedback endpoints."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.deps import get_db, paginate_query, pagination_params, serialize_value
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


def _apply_trade_date_range(stmt: object, *, start_date: date | None, end_date: date | None) -> object:
    if start_date is not None:
        stmt = stmt.where(PerformanceDaily.trade_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(PerformanceDaily.trade_date <= end_date)
    return stmt


def _build_chart_series(items: list[dict]) -> dict[str, list[dict[str, float | str | int]]]:
    def _series(metric_key: str) -> list[dict[str, float | str | int]]:
        return [{"x": item["trade_date"], "y": item[metric_key]} for item in items]

    return {
        "equity_curve": _series("cumulative_net_profit"),
        "daily_pnl": _series("net_profit"),
        "gross_profit": _series("gross_profit"),
        "gross_loss": _series("gross_loss"),
        "trade_count": _series("total_trades"),
        "drawdown": _series("max_drawdown"),
        "win_rate": _series("win_rate"),
    }


def _resolve_period_bounds(trade_date: date, group_by: Literal["day", "week", "month"]) -> tuple[date, date]:
    if group_by == "week":
        period_start = trade_date - timedelta(days=trade_date.weekday())
        period_end = period_start + timedelta(days=6)
        return period_start, period_end
    if group_by == "month":
        period_start = trade_date.replace(day=1)
        if period_start.month == 12:
            next_month = period_start.replace(year=period_start.year + 1, month=1, day=1)
        else:
            next_month = period_start.replace(month=period_start.month + 1, day=1)
        period_end = next_month - timedelta(days=1)
        return period_start, period_end
    return trade_date, trade_date


def _aggregate_chart_rows(rows: list[Any], group_by: Literal["day", "week", "month"]) -> list[dict[str, Any]]:
    grouped: dict[tuple[date, date], dict[str, Any]] = defaultdict(
        lambda: {
            "total_trades": 0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "net_profit": 0.0,
            "max_drawdown": 0.0,
            "weighted_win_rate_numerator": 0.0,
        }
    )

    for row in rows:
        trade_date = row.trade_date
        period_start, period_end = _resolve_period_bounds(trade_date, group_by)
        bucket = grouped[(period_start, period_end)]
        bucket["total_trades"] += int(row.total_trades or 0)
        bucket["gross_profit"] += float(row.gross_profit or 0.0)
        bucket["gross_loss"] += float(row.gross_loss or 0.0)
        bucket["net_profit"] += float(row.net_profit or 0.0)
        bucket["max_drawdown"] = max(bucket["max_drawdown"], float(row.max_drawdown or 0.0))
        bucket["weighted_win_rate_numerator"] += float(row.weighted_win_rate_numerator or 0.0)

    result: list[dict[str, Any]] = []
    for (period_start, period_end), bucket in sorted(grouped.items(), key=lambda item: item[0][0]):
        result.append(
            {
                "trade_date": serialize_value(period_start),
                "period_start": serialize_value(period_start),
                "period_end": serialize_value(period_end),
                **bucket,
            }
        )
    return result


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


@router.get("/performance/chart")
def get_performance_chart(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    group_by: Literal["day", "week", "month"] = Query(default="day"),
    db: Session = Depends(get_db),
) -> dict:
    if start_date is not None and end_date is not None and start_date > end_date:
        return {
            "items": [],
            "series": _build_chart_series([]),
            "summary": {
                "start_date": serialize_value(start_date),
                "end_date": serialize_value(end_date),
                "group_by": group_by,
                "points": 0,
                "total_trades": 0,
                "total_net_profit": 0.0,
            },
        }

    stmt = select(
        PerformanceDaily.trade_date.label("trade_date"),
        func.coalesce(func.sum(PerformanceDaily.total_trades), 0).label("total_trades"),
        func.coalesce(func.sum(PerformanceDaily.gross_profit), 0).label("gross_profit"),
        func.coalesce(func.sum(PerformanceDaily.gross_loss), 0).label("gross_loss"),
        func.coalesce(func.sum(PerformanceDaily.net_profit), 0).label("net_profit"),
        func.coalesce(func.max(PerformanceDaily.max_drawdown), 0).label("max_drawdown"),
        func.coalesce(func.sum(PerformanceDaily.win_rate * PerformanceDaily.total_trades), 0.0).label("weighted_win_rate_numerator"),
    ).group_by(PerformanceDaily.trade_date)
    stmt = _apply_trade_date_range(stmt, start_date=start_date, end_date=end_date).order_by(PerformanceDaily.trade_date.asc())

    rows = db.execute(stmt).all()
    aggregated_rows = _aggregate_chart_rows(list(rows), group_by)
    cumulative_net_profit = 0.0
    items: list[dict] = []
    total_trades = 0

    for row in aggregated_rows:
        trades = int(row["total_trades"] or 0)
        net_profit = float(row["net_profit"] or 0.0)
        cumulative_net_profit += net_profit
        total_trades += trades
        win_rate = (float(row["weighted_win_rate_numerator"] or 0.0) / trades) if trades > 0 else 0.0
        items.append(
            {
                "trade_date": serialize_value(row["trade_date"]),
                "period_start": serialize_value(row["period_start"]),
                "period_end": serialize_value(row["period_end"]),
                "total_trades": trades,
                "gross_profit": float(row["gross_profit"] or 0.0),
                "gross_loss": abs(float(row["gross_loss"] or 0.0)),
                "net_profit": net_profit,
                "cumulative_net_profit": cumulative_net_profit,
                "max_drawdown": float(row["max_drawdown"] or 0.0),
                "win_rate": win_rate,
            }
        )

    return {
        "items": items,
        "series": _build_chart_series(items),
        "summary": {
            "start_date": serialize_value(start_date),
            "end_date": serialize_value(end_date),
            "group_by": group_by,
            "points": len(items),
            "total_trades": total_trades,
            "total_net_profit": cumulative_net_profit,
        },
    }


@router.get("/performance/by-strategy")
def get_performance_by_strategy(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(PerformanceByStrategy).order_by(PerformanceByStrategy.created_at.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])


@router.get("/feedback/strategy")
def get_strategy_feedback(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(StrategyFeedbackEvent).order_by(StrategyFeedbackEvent.created_at.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])
