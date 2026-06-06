"""Signal endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.deps import get_db, model_to_dict, pagination_params
from src.infrastructure.database.models import (
    ExecutionDecision,
    ExecutionOrder,
    HistoricalEdgeValidation,
    Signal,
    SignalValidation,
)

router = APIRouter(prefix="/api/v1/signals", tags=["signals"])


def _latest_by_signal_id(rows: list[Any], *, signal_attr: str = "signal_id") -> dict[uuid.UUID, Any]:
    latest: dict[uuid.UUID, Any] = {}
    for row in rows:
        signal_id = getattr(row, signal_attr)
        latest.setdefault(signal_id, row)
    return latest


def _resolve_final_status(
    *,
    signal: Signal,
    validation: SignalValidation | None,
    edge: HistoricalEdgeValidation | None,
    decision: ExecutionDecision | None,
    order: ExecutionOrder | None,
) -> str:
    if order is not None:
        if order.status == "DRY_RUN":
            return "DRY_RUN"
        if order.status in {"FILLED", "SUBMITTED", "REJECTED", "FAILED", "CANCELLED"}:
            return f"ORDER_{order.status}"
        return "ORDER_CREATED"

    if decision is not None:
        if decision.decision in {"APPROVE", "APPROVE_AUTO", "APPROVED"}:
            return "APPROVED"
        if decision.decision == "DRY_RUN":
            return "DRY_RUN_APPROVED"
        if decision.decision == "MANUAL_APPROVAL":
            return "PENDING_MANUAL_APPROVAL"
        if decision.decision == "KILL_SWITCH":
            return "REJECTED"
        if decision.decision in {"REJECT", "WAIT", "REDUCE_RISK"}:
            return decision.decision
        return decision.decision

    if edge is not None and edge.passed is False:
        return "REJECTED"

    if validation is not None:
        if validation.status in {"REJECTED", "FAILED"}:
            return "REJECTED"
        if validation.status == "PASSED":
            return "PENDING_EXECUTION_DECISION"

    if signal.status in {"CREATED", "GENERATED"}:
        return "PENDING_DECISION"
    return str(signal.status)


def _build_signal_payload(
    signal: Signal,
    *,
    validation: SignalValidation | None = None,
    edge: HistoricalEdgeValidation | None = None,
    decision: ExecutionDecision | None = None,
    order: ExecutionOrder | None = None,
) -> dict[str, Any]:
    payload = model_to_dict(signal)
    final_status = _resolve_final_status(
        signal=signal,
        validation=validation,
        edge=edge,
        decision=decision,
        order=order,
    )
    payload["decision_summary"] = {
        "final_status": final_status,
        "validation_status": validation.status if validation else None,
        "validation_rejection_reason": validation.rejection_reason if validation else None,
        "validation_error_message": validation.error_message if validation else None,
        "historical_edge_passed": edge.passed if edge else None,
        "historical_edge_sample_size": edge.sample_size if edge else None,
        "historical_edge_win_rate": float(edge.win_rate) if edge else None,
        "execution_decision": decision.decision if decision else None,
        "execution_rejection_reason": decision.rejection_reason if decision else None,
        "order_status": order.status if order else None,
        "signal_validation_id": str(validation.id) if validation else None,
        "historical_edge_validation_id": str(edge.id) if edge else None,
        "execution_decision_id": str(decision.id) if decision else None,
        "execution_order_id": str(order.id) if order else None,
    }
    return payload


def _enrich_signals(db: Session, signals: list[Signal]) -> list[dict[str, Any]]:
    if not signals:
        return []

    signal_ids = [signal.id for signal in signals]
    validations = db.execute(
        select(SignalValidation)
        .where(SignalValidation.signal_id.in_(signal_ids))
        .order_by(SignalValidation.validated_at.desc(), SignalValidation.created_at.desc())
    ).scalars().all()
    edges = db.execute(
        select(HistoricalEdgeValidation)
        .where(HistoricalEdgeValidation.signal_id.in_(signal_ids))
        .order_by(HistoricalEdgeValidation.validated_at.desc(), HistoricalEdgeValidation.created_at.desc())
    ).scalars().all()
    decisions = db.execute(
        select(ExecutionDecision)
        .where(ExecutionDecision.signal_id.in_(signal_ids))
        .order_by(ExecutionDecision.created_at.desc())
    ).scalars().all()
    orders = db.execute(
        select(ExecutionOrder)
        .where(ExecutionOrder.signal_id.in_(signal_ids))
        .order_by(ExecutionOrder.created_at.desc())
    ).scalars().all()

    validation_by_signal_id = _latest_by_signal_id(list(validations))
    edge_by_signal_id = _latest_by_signal_id(list(edges))
    decision_by_signal_id = _latest_by_signal_id(list(decisions))
    order_by_signal_id = _latest_by_signal_id(list(orders))

    return [
        _build_signal_payload(
            signal,
            validation=validation_by_signal_id.get(signal.id),
            edge=edge_by_signal_id.get(signal.id),
            decision=decision_by_signal_id.get(signal.id),
            order=order_by_signal_id.get(signal.id),
        )
        for signal in signals
    ]


@router.get("/latest")
def get_latest_signal(db: Session = Depends(get_db)) -> dict:
    signal = db.execute(select(Signal).order_by(Signal.signal_time.desc()).limit(1)).scalar_one_or_none()
    return {"signal": _enrich_signals(db, [signal])[0] if signal else None}


@router.get("")
def get_signals(p: dict[str, int] = Depends(pagination_params), db: Session = Depends(get_db)) -> dict:
    stmt = select(Signal).order_by(Signal.signal_time.desc())
    signals = db.execute(stmt.limit(p["limit"]).offset(p["offset"])).scalars().all()
    total = db.execute(select(func.count()).select_from(Signal)).scalar_one()
    return {
        "items": _enrich_signals(db, list(signals)),
        "total": int(total),
        "limit": p["limit"],
        "offset": p["offset"],
    }


@router.get("/{signal_id}")
def get_signal_by_id(signal_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    signal = db.get(Signal, signal_id)
    return {"signal": _enrich_signals(db, [signal])[0] if signal else None}
