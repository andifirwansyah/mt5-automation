"""Account endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.deps import get_db, model_to_dict, paginate_query, pagination_params
from src.infrastructure.database.models import AccountSnapshot, TradingAccount

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


@router.get("/current")
def get_current_account(db: Session = Depends(get_db)) -> dict:
    account = db.execute(select(TradingAccount).order_by(TradingAccount.updated_at.desc()).limit(1)).scalar_one_or_none()
    return {"account": model_to_dict(account) if account else None}


@router.get("/snapshots")
def get_account_snapshots(
    p: dict[str, int] = Depends(pagination_params),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(AccountSnapshot).order_by(AccountSnapshot.snapshot_time.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])


@router.get("/current/balance")
def get_current_balance(db: Session = Depends(get_db)) -> dict:
    snapshot = db.execute(select(AccountSnapshot).order_by(AccountSnapshot.snapshot_time.desc()).limit(1)).scalar_one_or_none()
    if snapshot is None:
        return {"balance": None}

    return {
        "balance": {
            "account_id": str(snapshot.account_id),
            "balance": float(snapshot.balance),
            "equity": float(snapshot.equity),
            "margin": float(snapshot.margin),
            "free_margin": float(snapshot.free_margin),
            "margin_level": float(snapshot.margin_level),
            "profit": float(snapshot.profit),
            "snapshot_time": snapshot.snapshot_time.isoformat(),
        }
    }
