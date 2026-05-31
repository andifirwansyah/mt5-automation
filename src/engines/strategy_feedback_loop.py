"""Strategy feedback loop engine."""

from __future__ import annotations

from sqlalchemy import select

from src.config.settings import AppSettings, get_settings
from src.infrastructure.database.models import PerformanceByStrategy
from src.repositories.performance_repository import PerformanceRepository


class StrategyFeedbackLoop:
    """Generate strategy feedback events based on latest performance stats."""

    def __init__(self, performance_repository: PerformanceRepository, settings: AppSettings | None = None) -> None:
        self.performance_repository = performance_repository
        self.settings = settings or get_settings()

    def run_cycle(self) -> dict[str, int]:
        session = self.performance_repository.session
        rows = session.execute(
            select(PerformanceByStrategy).order_by(PerformanceByStrategy.period_end.desc())
        ).scalars().all()

        created_events = 0
        for row in rows:
            total_trades = int(row.total_trades or 0)
            win_rate = float(row.win_rate or 0.0)
            details = row.details or {}
            drawdown = float(details.get("max_drawdown", 0.0))

            recommendation = "KEEP_ACTIVE"
            reason = "Strategy performance healthy"

            if total_trades < int(self.settings.feedback_min_trades):
                recommendation = "NEED_MORE_DATA"
                reason = f"total_trades({total_trades}) < feedback_min_trades({self.settings.feedback_min_trades})"
            elif win_rate < float(self.settings.feedback_low_win_rate) and drawdown >= float(self.settings.feedback_high_drawdown):
                recommendation = "DISABLE_TEMPORARILY"
                reason = "Low win rate and high drawdown"
            elif win_rate < float(self.settings.feedback_low_win_rate):
                recommendation = "REDUCE_RISK"
                reason = "Low win rate"
            elif drawdown >= float(self.settings.feedback_high_drawdown):
                recommendation = "REVIEW_PARAMETERS"
                reason = "High drawdown"

            if recommendation == "KEEP_ACTIVE" and total_trades >= int(self.settings.feedback_min_trades):
                # keep clean; only create events when action is needed or data insufficient
                continue

            score = max(0.0, min(1.0, win_rate))
            self.performance_repository.create_strategy_feedback_event(
                strategy_id=row.strategy_id,
                signal_id=None,
                event_type=recommendation,
                score=score,
                details={
                    "reason": reason,
                    "win_rate": win_rate,
                    "drawdown": drawdown,
                    "total_trades": total_trades,
                    "auto_apply_strategy_feedback": bool(self.settings.auto_apply_strategy_feedback),
                },
            )
            created_events += 1

        self.performance_repository.session.commit()
        return {"created_feedback_events": created_events}
