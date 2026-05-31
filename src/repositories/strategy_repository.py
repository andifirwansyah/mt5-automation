"""Repository for strategy catalog and selection tables."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.infrastructure.database.models import Strategy, StrategyConfig, StrategySelection


class StrategyRepository:
    """CRUD/query repository for strategy-related tables."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_active_strategies(self) -> list[Strategy]:
        stmt = select(Strategy).where(Strategy.is_active.is_(True)).order_by(Strategy.code.asc())
        return list(self.session.execute(stmt).scalars().all())

    def get_active_strategy_configs(
        self,
        strategy_id: uuid.UUID | None = None,
        symbol_id: uuid.UUID | None = None,
        timeframe_id: uuid.UUID | None = None,
    ) -> list[StrategyConfig]:
        stmt = select(StrategyConfig).where(StrategyConfig.is_active.is_(True))
        if strategy_id is not None:
            stmt = stmt.where(StrategyConfig.strategy_id == strategy_id)
        if symbol_id is not None:
            stmt = stmt.where((StrategyConfig.symbol_id == symbol_id) | (StrategyConfig.symbol_id.is_(None)))
        if timeframe_id is not None:
            stmt = stmt.where((StrategyConfig.timeframe_id == timeframe_id) | (StrategyConfig.timeframe_id.is_(None)))
        return list(self.session.execute(stmt).scalars().all())

    def create_strategy_selection(
        self,
        trace_id: uuid.UUID,
        symbol_id: uuid.UUID,
        timeframe_id: uuid.UUID,
        strategy_id: uuid.UUID,
        score: float,
        regime_id: uuid.UUID | None = None,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> StrategySelection:
        entity = StrategySelection(
            trace_id=trace_id,
            symbol_id=symbol_id,
            timeframe_id=timeframe_id,
            strategy_id=strategy_id,
            regime_id=regime_id,
            score=score,
            reason=reason,
            details=details or {},
        )
        self.session.add(entity)
        self.session.flush()
        return entity
