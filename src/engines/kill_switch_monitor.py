"""Kill switch monitor engine for safety hard-limits enforcement."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, func, select

from src.config.settings import AppSettings, get_settings
from src.infrastructure.database.models import ExecutionOrder, Position
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories.safety_repository import SafetyRepository


class KillSwitchMonitor(PipelineStep):
    """Evaluate kill-switch and runtime safety limits before trading."""

    @property
    def name(self) -> str:
        return "KillSwitchMonitor"

    def __init__(self, safety_repository: SafetyRepository, settings: AppSettings | None = None) -> None:
        self.safety_repository = safety_repository
        self.settings = settings or get_settings()

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    def _today_bounds(self) -> tuple[datetime, datetime]:
        now = self._utc_now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(day=start.day) + (now - now.replace(hour=0, minute=0, second=0, microsecond=0))
        return start, now

    def run(self, context: TradingContext) -> TradingContext:
        active = self.safety_repository.get_active_kill_switch()
        if active is not None:
            self.safety_repository.create_safety_event(
                event_type="KILL_SWITCH_ACTIVE",
                severity="HIGH",
                status="ACTIVE",
                message="Kill switch already active",
                related_trace_id=context.trace_id,
                details={"kill_switch_id": str(active.id)},
            )
            self.safety_repository.session.commit()
            context.reject("KILL_SWITCH_ACTIVE", {"kill_switch_id": str(active.id)})
            return context

        session = self.safety_repository.session
        start_day, now = self._today_bounds()

        violations: list[dict[str, str]] = []

        # Max trades per day
        trades_today = int(
            session.execute(
                select(func.count(ExecutionOrder.id)).where(
                    and_(ExecutionOrder.created_at >= start_day, ExecutionOrder.created_at <= now)
                )
            ).scalar_one()
        )
        if trades_today >= int(self.settings.max_trades_per_day):
            violations.append({"rule": "MAX_TRADES_PER_DAY", "value": str(trades_today)})

        # Max open positions
        open_positions = int(session.execute(select(func.count(Position.id)).where(Position.status == "OPEN")).scalar_one())
        if open_positions >= int(self.settings.max_open_positions):
            violations.append({"rule": "MAX_OPEN_POSITIONS", "value": str(open_positions)})

        # Max consecutive losses
        recent_closed = session.execute(
            select(Position.profit).where(Position.status == "CLOSED").order_by(Position.closed_at.desc()).limit(50)
        ).all()
        consecutive_losses = 0
        for (profit,) in recent_closed:
            if float(profit or 0.0) < 0:
                consecutive_losses += 1
            else:
                break
        if consecutive_losses >= int(self.settings.max_consecutive_losses):
            violations.append({"rule": "MAX_CONSECUTIVE_LOSSES", "value": str(consecutive_losses)})

        # Daily loss and margin checks from latest account snapshot-like data in context
        account_info = (context.ingestion_result or {}).get("account_info") or {}
        profit = float(account_info.get("profit", 0.0))
        margin_level = float(account_info.get("margin_level", 0.0))

        if abs(min(profit, 0.0)) >= float(self.settings.max_daily_loss):
            violations.append({"rule": "MAX_DAILY_LOSS", "value": str(profit)})

        if margin_level > 0 and margin_level < float(self.settings.min_margin_level):
            violations.append({"rule": "LOW_MARGIN_LEVEL", "value": str(margin_level)})

        if violations:
            reason = "; ".join([f"{v['rule']}={v['value']}" for v in violations])
            self.safety_repository.activate_kill_switch(
                reason=reason,
                activated_by="KillSwitchMonitor",
                details={"violations": violations, "trace_id": str(context.trace_id)},
            )
            self.safety_repository.create_safety_event(
                event_type="KILL_SWITCH_TRIGGERED",
                severity="CRITICAL",
                status="TRIGGERED",
                message="Kill switch activated by safety rule violations",
                related_trace_id=context.trace_id,
                details={"violations": violations},
            )
            self.safety_repository.session.commit()
            context.reject("KILL_SWITCH_ACTIVE", {"violations": violations})
            return context

        self.safety_repository.create_safety_event(
            event_type="KILL_SWITCH_CHECK",
            severity="INFO",
            status="PASSED",
            message="Kill switch monitor checks passed",
            related_trace_id=context.trace_id,
            details={
                "trades_today": trades_today,
                "open_positions": open_positions,
                "consecutive_losses": consecutive_losses,
                "profit": profit,
                "margin_level": margin_level,
            },
        )
        self.safety_repository.session.commit()
        return context
