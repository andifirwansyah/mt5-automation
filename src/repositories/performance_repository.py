"""Repository for performance analytics tables."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.infrastructure.database.models import PerformanceByStrategy, PerformanceDaily, StrategyFeedbackEvent


class PerformanceRepository:
    """CRUD/query repository for performance entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_performance_daily(
        self,
        account_id: uuid.UUID,
        trade_date: date,
        gross_profit: float,
        gross_loss: float,
        net_profit: float,
        win_rate: float,
        total_trades: int,
        max_drawdown: float,
        details: dict[str, Any] | None = None,
    ) -> PerformanceDaily:
        stmt = (
            select(PerformanceDaily)
            .where(PerformanceDaily.account_id == account_id, PerformanceDaily.trade_date == trade_date)
            .limit(1)
        )
        entity = self.session.execute(stmt).scalar_one_or_none()
        if entity is None:
            entity = PerformanceDaily(
                account_id=account_id,
                trade_date=trade_date,
                gross_profit=gross_profit,
                gross_loss=gross_loss,
                net_profit=net_profit,
                win_rate=win_rate,
                total_trades=total_trades,
                max_drawdown=max_drawdown,
                details=details or {},
            )
        else:
            entity.gross_profit = gross_profit
            entity.gross_loss = gross_loss
            entity.net_profit = net_profit
            entity.win_rate = win_rate
            entity.total_trades = total_trades
            entity.max_drawdown = max_drawdown
            entity.details = details or entity.details

        self.session.add(entity)
        self.session.flush()
        return entity

    def get_performance_daily(self, account_id: uuid.UUID, trade_date: date) -> PerformanceDaily | None:
        stmt = (
            select(PerformanceDaily)
            .where(PerformanceDaily.account_id == account_id, PerformanceDaily.trade_date == trade_date)
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def create_performance_by_strategy(
        self,
        strategy_id: uuid.UUID,
        period_start: date,
        period_end: date,
        total_trades: int,
        win_rate: float,
        net_profit: float,
        profit_factor: float,
        account_id: uuid.UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> PerformanceByStrategy:
        entity = PerformanceByStrategy(
            strategy_id=strategy_id,
            account_id=account_id,
            period_start=period_start,
            period_end=period_end,
            total_trades=total_trades,
            win_rate=win_rate,
            net_profit=net_profit,
            profit_factor=profit_factor,
            details=details or {},
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def create_strategy_feedback_event(
        self,
        strategy_id: uuid.UUID,
        event_type: str,
        score: float,
        signal_id: uuid.UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> StrategyFeedbackEvent:
        entity = StrategyFeedbackEvent(
            strategy_id=strategy_id,
            signal_id=signal_id,
            event_type=event_type,
            score=score,
            details=details or {},
        )
        self.session.add(entity)
        self.session.flush()
        return entity
