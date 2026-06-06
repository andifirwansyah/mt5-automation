"""Repository for signal and validation tables."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.infrastructure.database.models import HistoricalEdgeValidation, Signal, SignalValidation


class SignalRepository:
    """CRUD/query repository for signal domain."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_signal(
        self,
        trace_id: uuid.UUID,
        symbol_id: uuid.UUID,
        timeframe_id: uuid.UUID,
        strategy_id: uuid.UUID,
        direction: str,
        status: str,
        signal_time: datetime,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        lot_size: float,
        confidence: float,
        features: dict[str, Any] | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> Signal:
        entity = Signal(
            trace_id=trace_id,
            symbol_id=symbol_id,
            timeframe_id=timeframe_id,
            strategy_id=strategy_id,
            direction=direction,
            status=status,
            signal_time=signal_time,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            lot_size=lot_size,
            confidence=confidence,
            features=features or {},
            raw_payload=raw_payload or {},
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def create_signal_validation(
        self,
        signal_id: uuid.UUID,
        validator_name: str,
        status: str,
        validated_at: datetime,
        rejection_reason: str | None = None,
        error_message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> SignalValidation:
        entity = SignalValidation(
            signal_id=signal_id,
            validator_name=validator_name,
            status=status,
            validated_at=validated_at,
            rejection_reason=rejection_reason,
            error_message=error_message,
            details=details or {},
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def create_historical_edge_validation(
        self,
        signal_id: uuid.UUID,
        strategy_id: uuid.UUID,
        sample_size: int,
        win_rate: float,
        expectancy: float,
        passed: bool,
        validated_at: datetime,
        details: dict[str, Any] | None = None,
    ) -> HistoricalEdgeValidation:
        entity = HistoricalEdgeValidation(
            signal_id=signal_id,
            strategy_id=strategy_id,
            sample_size=sample_size,
            win_rate=win_rate,
            expectancy=expectancy,
            passed=passed,
            validated_at=validated_at,
            details=details or {},
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def get_latest_signal(
        self,
        symbol_id: uuid.UUID | None = None,
        timeframe_id: uuid.UUID | None = None,
    ) -> Signal | None:
        stmt = select(Signal)
        if symbol_id is not None:
            stmt = stmt.where(Signal.symbol_id == symbol_id)
        if timeframe_id is not None:
            stmt = stmt.where(Signal.timeframe_id == timeframe_id)
        stmt = stmt.order_by(Signal.signal_time.desc()).limit(1)
        return self.session.execute(stmt).scalar_one_or_none()

    def count_signals_by_candle(
        self,
        symbol_id: uuid.UUID,
        timeframe_id: uuid.UUID,
        signal_time: datetime,
        exclude_signal_id: uuid.UUID | None = None,
    ) -> int:
        stmt = select(func.count(Signal.id)).where(
            Signal.symbol_id == symbol_id,
            Signal.timeframe_id == timeframe_id,
            Signal.signal_time == signal_time,
        )
        if exclude_signal_id is not None:
            stmt = stmt.where(Signal.id != exclude_signal_id)
        return int(self.session.execute(stmt).scalar_one())

    def count_recent_signals(
        self,
        symbol_id: uuid.UUID,
        timeframe_id: uuid.UUID,
        since: datetime,
        exclude_signal_id: uuid.UUID | None = None,
    ) -> int:
        stmt = select(func.count(Signal.id)).where(
            Signal.symbol_id == symbol_id,
            Signal.timeframe_id == timeframe_id,
            Signal.signal_time >= since,
        )
        if exclude_signal_id is not None:
            stmt = stmt.where(Signal.id != exclude_signal_id)
        return int(self.session.execute(stmt).scalar_one())
