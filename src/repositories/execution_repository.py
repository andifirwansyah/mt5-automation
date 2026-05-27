"""Repository for execution pipeline tables."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from src.infrastructure.database.models import ApprovalRequest, BrokerHealthCheck, ExecutionDecision, ExecutionOrder


class ExecutionRepository:
    """CRUD/query repository for execution entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_broker_health_check(
        self,
        is_connected: bool,
        is_trade_allowed: bool,
        is_healthy: bool,
        checked_at: datetime,
        symbol_id: uuid.UUID | None = None,
        spread: float | None = None,
        latency_ms: int | None = None,
        details: dict[str, Any] | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> BrokerHealthCheck:
        entity = BrokerHealthCheck(
            symbol_id=symbol_id,
            is_connected=is_connected,
            is_trade_allowed=is_trade_allowed,
            is_healthy=is_healthy,
            spread=spread,
            latency_ms=latency_ms,
            details=details or {},
            raw_payload=raw_payload or {},
            checked_at=checked_at,
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def create_execution_decision(
        self,
        signal_id: uuid.UUID,
        trace_id: uuid.UUID,
        decision: str,
        rejection_reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> ExecutionDecision:
        entity = ExecutionDecision(
            signal_id=signal_id,
            trace_id=trace_id,
            decision=decision,
            rejection_reason=rejection_reason,
            details=details or {},
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def create_approval_request(
        self,
        execution_decision_id: uuid.UUID,
        approval_required: bool,
        status: str,
        requested_at: datetime,
        requested_by: str | None = None,
        approved_by: str | None = None,
        details: dict[str, Any] | None = None,
        responded_at: datetime | None = None,
    ) -> ApprovalRequest:
        entity = ApprovalRequest(
            execution_decision_id=execution_decision_id,
            approval_required=approval_required,
            status=status,
            requested_by=requested_by,
            approved_by=approved_by,
            details=details or {},
            requested_at=requested_at,
            responded_at=responded_at,
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def create_execution_order(
        self,
        signal_id: uuid.UUID,
        symbol_id: uuid.UUID,
        side: str,
        order_type: str,
        volume_lot: float,
        requested_price: float,
        stop_loss: float,
        take_profit: float,
        deviation: int,
        status: str,
        execution_decision_id: uuid.UUID | None = None,
        mt5_order_ticket: int | None = None,
        broker_response: dict[str, Any] | None = None,
        error_message: str | None = None,
        executed_at: datetime | None = None,
    ) -> ExecutionOrder:
        entity = ExecutionOrder(
            signal_id=signal_id,
            execution_decision_id=execution_decision_id,
            symbol_id=symbol_id,
            mt5_order_ticket=mt5_order_ticket,
            side=side,
            order_type=order_type,
            volume_lot=volume_lot,
            requested_price=requested_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            deviation=deviation,
            status=status,
            broker_response=broker_response or {},
            error_message=error_message,
            executed_at=executed_at,
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def update_execution_order_result(
        self,
        order_id: uuid.UUID,
        status: str,
        mt5_order_ticket: int | None = None,
        broker_response: dict[str, Any] | None = None,
        error_message: str | None = None,
        executed_at: datetime | None = None,
    ) -> ExecutionOrder | None:
        entity = self.session.get(ExecutionOrder, order_id)
        if entity is None:
            return None

        entity.status = status
        entity.mt5_order_ticket = mt5_order_ticket or entity.mt5_order_ticket
        entity.broker_response = broker_response or entity.broker_response
        entity.error_message = error_message
        entity.executed_at = executed_at or entity.executed_at
        self.session.add(entity)
        self.session.flush()
        return entity
