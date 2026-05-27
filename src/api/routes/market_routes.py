"""Market data endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from src.api.deps import get_db, model_to_dict, paginate_query, pagination_params
from src.infrastructure.database.models import Candle, DataQualityCheck, MarketEvent, Symbol, TickSnapshot, Timeframe

router = APIRouter(prefix="/api/v1", tags=["market"])


@router.get("/symbols")
def get_symbols(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(Symbol).order_by(Symbol.name.asc())
    return paginate_query(db, stmt, p["limit"], p["offset"])


@router.get("/market/candles")
def get_candles(
    symbol: str = Query(...),
    timeframe: str = Query(...),
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> dict:
    sym = db.execute(select(Symbol).where(Symbol.name == symbol)).scalar_one_or_none()
    tf = db.execute(select(Timeframe).where(Timeframe.code == timeframe)).scalar_one_or_none()
    if not sym or not tf:
        return {"items": [], "total": 0, "limit": limit, "offset": 0}
    stmt = (
        select(Candle)
        .where(and_(Candle.symbol_id == sym.id, Candle.timeframe_id == tf.id))
        .order_by(Candle.open_time.desc())
    )
    return paginate_query(db, stmt, limit, 0)


@router.get("/market/ticks/latest")
def get_latest_tick(symbol: str = Query(...), db: Session = Depends(get_db)) -> dict:
    sym = db.execute(select(Symbol).where(Symbol.name == symbol)).scalar_one_or_none()
    if not sym:
        return {"tick": None}
    tick = db.execute(select(TickSnapshot).where(TickSnapshot.symbol_id == sym.id).order_by(TickSnapshot.event_time.desc()).limit(1)).scalar_one_or_none()
    return {"tick": model_to_dict(tick) if tick else None}


@router.get("/market/data-quality")
def get_data_quality(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(DataQualityCheck).order_by(DataQualityCheck.checked_at.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])


@router.get("/market/events")
def get_market_events(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(MarketEvent).order_by(MarketEvent.created_at.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])
