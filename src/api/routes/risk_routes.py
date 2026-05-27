"""Risk endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.deps import get_db, model_to_dict, paginate_query, pagination_params
from src.infrastructure.database.models import RiskAssessment

router = APIRouter(prefix="/api/v1/risk", tags=["risk"])


@router.get("/latest")
def get_latest_risk(db: Session = Depends(get_db)) -> dict:
    row = db.execute(select(RiskAssessment).order_by(RiskAssessment.assessed_at.desc()).limit(1)).scalar_one_or_none()
    return {"risk": model_to_dict(row) if row else None}


@router.get("/assessments")
def get_risk_assessments(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(RiskAssessment).order_by(RiskAssessment.assessed_at.desc())
    return paginate_query(db, stmt, p["limit"], p["offset"])
