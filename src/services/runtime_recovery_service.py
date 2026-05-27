"""Runtime recovery service for startup safety and state restoration."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, func, select

from src.infrastructure.database.models import ExecutionOrder, Position
from src.repositories.bot_repository import BotRepository
from src.repositories.execution_repository import ExecutionRepository
from src.repositories.safety_repository import SafetyRepository
from src.services.position_sync_service import PositionSyncService
from src.services.runtime_state_service import RuntimeStateService


class RuntimeRecoveryService:
    """Recover startup runtime baseline with safety-first checks."""

    def __init__(
        self,
        runtime_state_service: RuntimeStateService,
        position_sync_service: PositionSyncService,
        safety_repository: SafetyRepository,
        bot_repository: BotRepository,
        execution_repository: ExecutionRepository,
        account_id: uuid.UUID,
    ) -> None:
        self.runtime_state_service = runtime_state_service
        self.position_sync_service = position_sync_service
        self.safety_repository = safety_repository
        self.bot_repository = bot_repository
        self.execution_repository = execution_repository
        self.account_id = account_id

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    def _load_daily_risk_state(self) -> dict[str, float | int]:
        session = self.execution_repository.session
        now = self._utc_now()
        start_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

        trades_today = int(
            session.execute(
                select(func.count(ExecutionOrder.id)).where(
                    and_(ExecutionOrder.created_at >= start_day, ExecutionOrder.created_at <= now)
                )
            ).scalar_one()
        )

        realized_pnl = float(
            session.execute(
                select(func.coalesce(func.sum(Position.profit), 0.0)).where(
                    and_(
                        Position.closed_at.is_not(None),
                        Position.closed_at >= start_day,
                        Position.closed_at <= now,
                    )
                )
            ).scalar_one()
            or 0.0
        )

        recent_closed = session.execute(
            select(Position.profit).where(Position.status == "CLOSED").order_by(Position.closed_at.desc()).limit(50)
        ).all()

        consecutive_losses = 0
        for (profit,) in recent_closed:
            if float(profit or 0.0) < 0:
                consecutive_losses += 1
            else:
                break

        return {
            "trades_today": trades_today,
            "realized_pnl_today": realized_pnl,
            "consecutive_losses": consecutive_losses,
        }

    def run_startup_recovery(self) -> dict[str, object]:
        synced_positions = self.position_sync_service.sync_open_positions(account_id=self.account_id)
        kill_switch_active = self.safety_repository.get_active_kill_switch() is not None
        daily_risk_state = self._load_daily_risk_state()

        interrupted_count = self.bot_repository.mark_stale_engine_runs_interrupted(max_age_minutes=15)
        pending_approvals = self.execution_repository.count_pending_approval_requests()
        duplicate_execution_risk = self.execution_repository.count_duplicate_execution_risk()

        if pending_approvals > 0:
            self.safety_repository.create_safety_event(
                event_type="PENDING_APPROVAL_DETECTED",
                severity="MEDIUM",
                status="ACTIVE",
                message=f"Detected pending approval requests: {pending_approvals}",
                details={"pending_approvals": pending_approvals},
            )

        if duplicate_execution_risk > 0:
            self.safety_repository.create_safety_event(
                event_type="DUPLICATE_EXECUTION_RISK",
                severity="HIGH",
                status="ACTIVE",
                message=f"Detected duplicate execution risk count={duplicate_execution_risk}",
                details={"duplicate_execution_risk": duplicate_execution_risk},
            )

        self.bot_repository.session.commit()

        self.runtime_state_service.set_state("recovery_last_run_at", self._utc_now().isoformat())
        self.runtime_state_service.set_state("recovery_kill_switch_active", kill_switch_active)
        self.runtime_state_service.set_state("recovery_daily_risk_state", daily_risk_state)
        self.runtime_state_service.set_state("recovery_pending_approvals", pending_approvals)
        self.runtime_state_service.set_state("recovery_duplicate_execution_risk", duplicate_execution_risk)
        self.runtime_state_service.set_state("recovery_interrupted_engine_runs", interrupted_count)

        return {
            "synced_positions": len(synced_positions),
            "kill_switch_active": kill_switch_active,
            "daily_risk_state": daily_risk_state,
            "interrupted_engine_runs": interrupted_count,
            "pending_approvals": pending_approvals,
            "duplicate_execution_risk": duplicate_execution_risk,
        }
