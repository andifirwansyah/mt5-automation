"""Regime endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from src.api.deps import get_db, model_to_dict, paginate_query, pagination_params
from src.infrastructure.database.models import MarketRegime, Symbol, Timeframe

router = APIRouter(prefix="/api/v1/regimes", tags=["regimes"])


@router.get("/latest")
def get_latest_regime(symbol: str = Query(...), timeframe: str = Query(...), db: Session = Depends(get_db)) -> dict:
    sym = db.execute(select(Symbol).where(Symbol.name == symbol)).scalar_one_or_none()
    tf = db.execute(select(Timeframe).where(Timeframe.code == timeframe)).scalar_one_or_none()
    if not sym or not tf:
        return {"regime": None}
    regime = (
        db.execute(
            select(MarketRegime)
            .where(and_(MarketRegime.symbol_id == sym.id, MarketRegime.timeframe_id == tf.id))
            .order_by(MarketRegime.detected_at.desc())
            .limit(1)
        ).scalar_one_or_none()
    )
    return {"regime": model_to_dict(regime) if regime else None}


@router.get("/history")
def get_regime_history(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(MarketRegime).order_by(MarketRegime.detected_at.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])
