"""Repository for market data and market-event tables."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.infrastructure.database.models import Candle, DataQualityCheck, Symbol, TickSnapshot, Timeframe


class MarketRepository:
    """CRUD/query repository for market domain tables."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_symbol(
        self,
        name: str,
        asset_class: str = "FOREX",
        digits: int = 5,
        point: float = 0.00001,
        is_active: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> Symbol:
        stmt = select(Symbol).where(Symbol.name == name).limit(1)
        symbol = self.session.execute(stmt).scalar_one_or_none()
        if symbol is not None:
            return symbol

        symbol = Symbol(
            name=name,
            asset_class=asset_class,
            digits=digits,
            point=point,
            is_active=is_active,
            metadata_json=metadata or {},
        )
        self.session.add(symbol)
        self.session.flush()
        return symbol

    def get_timeframe_by_code(self, code: str) -> Timeframe | None:
        stmt = select(Timeframe).where(Timeframe.code == code).limit(1)
        return self.session.execute(stmt).scalar_one_or_none()

    def upsert_candle(
        self,
        symbol_id: uuid.UUID,
        timeframe_id: uuid.UUID,
        open_time: datetime,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
        tick_volume: int,
        spread: int | None = None,
        real_volume: int | None = None,
        features: dict[str, Any] | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> Candle:
        stmt = (
            select(Candle)
            .where(
                Candle.symbol_id == symbol_id,
                Candle.timeframe_id == timeframe_id,
                Candle.open_time == open_time,
            )
            .limit(1)
        )
        candle = self.session.execute(stmt).scalar_one_or_none()
        if candle is None:
            candle = Candle(
                symbol_id=symbol_id,
                timeframe_id=timeframe_id,
                open_time=open_time,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                tick_volume=tick_volume,
                spread=spread,
                real_volume=real_volume,
                features=features or {},
                raw_payload=raw_payload or {},
            )
        else:
            candle.open_price = open_price
            candle.high_price = high_price
            candle.low_price = low_price
            candle.close_price = close_price
            candle.tick_volume = tick_volume
            candle.spread = spread
            candle.real_volume = real_volume
            candle.features = features or candle.features
            candle.raw_payload = raw_payload or candle.raw_payload

        self.session.add(candle)
        self.session.flush()
        return candle

    def bulk_upsert_candles(self, candles: list[dict[str, Any]]) -> list[Candle]:
        entities: list[Candle] = []
        for row in candles:
            entities.append(
                self.upsert_candle(
                    symbol_id=row["symbol_id"],
                    timeframe_id=row["timeframe_id"],
                    open_time=row["open_time"],
                    open_price=row["open_price"],
                    high_price=row["high_price"],
                    low_price=row["low_price"],
                    close_price=row["close_price"],
                    tick_volume=row["tick_volume"],
                    spread=row.get("spread"),
                    real_volume=row.get("real_volume"),
                    features=row.get("features"),
                    raw_payload=row.get("raw_payload"),
                )
            )
        return entities

    def create_tick_snapshot(
        self,
        symbol_id: uuid.UUID,
        event_time: datetime,
        bid: float,
        ask: float,
        last: float | None = None,
        spread: float | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> TickSnapshot:
        entity = TickSnapshot(
            symbol_id=symbol_id,
            event_time=event_time,
            bid=bid,
            ask=ask,
            last=last,
            spread=spread,
            raw_payload=raw_payload or {},
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def create_data_quality_check(
        self,
        check_name: str,
        status: str,
        checked_at: datetime,
        symbol_id: uuid.UUID | None = None,
        timeframe_id: uuid.UUID | None = None,
        rejection_reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> DataQualityCheck:
        entity = DataQualityCheck(
            symbol_id=symbol_id,
            timeframe_id=timeframe_id,
            check_name=check_name,
            status=status,
            checked_at=checked_at,
            rejection_reason=rejection_reason,
            details=details or {},
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def get_latest_candles(self, symbol_id: uuid.UUID, timeframe_id: uuid.UUID, limit: int = 200) -> list[Candle]:
        stmt = (
            select(Candle)
            .where(Candle.symbol_id == symbol_id, Candle.timeframe_id == timeframe_id)
            .order_by(Candle.open_time.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())
