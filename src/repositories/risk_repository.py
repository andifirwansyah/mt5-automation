"""Repository for risk and simulation tables."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from src.infrastructure.database.models import PreTradeSimulation, RiskAssessment


class RiskRepository:
    """CRUD repository for risk-related entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_risk_assessment(
        self,
        signal_id: uuid.UUID,
        risk_per_trade_pct: float,
        max_daily_loss_pct: float,
        position_size_lot: float,
        stop_loss_pips: float,
        take_profit_pips: float,
        risk_reward_ratio: float,
        passed: bool,
        assessed_at: datetime,
        rejection_reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> RiskAssessment:
        entity = RiskAssessment(
            signal_id=signal_id,
            risk_per_trade_pct=risk_per_trade_pct,
            max_daily_loss_pct=max_daily_loss_pct,
            position_size_lot=position_size_lot,
            stop_loss_pips=stop_loss_pips,
            take_profit_pips=take_profit_pips,
            risk_reward_ratio=risk_reward_ratio,
            passed=passed,
            assessed_at=assessed_at,
            rejection_reason=rejection_reason,
            details=details or {},
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def create_pre_trade_simulation(
        self,
        signal_id: uuid.UUID,
        expected_profit: float,
        expected_drawdown: float,
        slippage_estimate: float,
        passed: bool,
        simulated_at: datetime,
        rejection_reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> PreTradeSimulation:
        entity = PreTradeSimulation(
            signal_id=signal_id,
            expected_profit=expected_profit,
            expected_drawdown=expected_drawdown,
            slippage_estimate=slippage_estimate,
            passed=passed,
            simulated_at=simulated_at,
            rejection_reason=rejection_reason,
            details=details or {},
        )
        self.session.add(entity)
        self.session.flush()
        return entity
