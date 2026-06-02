"""Performance analyzer engine."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timezone

from sqlalchemy import and_, select

from src.infrastructure.database.models import ExecutionOrder, Position, Signal
from src.repositories.performance_repository import PerformanceRepository


class PerformanceAnalyzer:
    """Compute daily and per-strategy performance metrics from closed trades."""

    def __init__(self, performance_repository: PerformanceRepository) -> None:
        self.performance_repository = performance_repository

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _safe_div(num: float, den: float) -> float:
        return (num / den) if den != 0 else 0.0

    @staticmethod
    def _calculate_max_drawdown(profits: list[float]) -> float:
        if not profits:
            return 0.0
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for p in profits:
            equity += p
            peak = max(peak, equity)
            drawdown = peak - equity
            max_dd = max(max_dd, drawdown)
        return max_dd

    def run_cycle(self, reference_time: datetime | None = None) -> dict[str, float | int]:
        now = reference_time or self._utc_now()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        session = self.performance_repository.session
        summary_rows = session.execute(
            select(
                Position.id,
                Position.account_id,
                Position.profit,
                Position.closed_at,
            )
            .where(and_(Position.status == "CLOSED", Position.closed_at >= day_start, Position.closed_at <= now))
        ).all()

        profits = [float(r.profit or 0.0) for r in summary_rows]
        wins = [p for p in profits if p > 0]
        losses = [p for p in profits if p < 0]

        total_trades = len(profits)
        winning_trades = len(wins)
        losing_trades = len(losses)
        win_rate = self._safe_div(winning_trades, total_trades)
        gross_profit = sum(wins)
        gross_loss = sum(losses)
        net_profit = gross_profit + gross_loss
        profit_factor = self._safe_div(gross_profit, abs(gross_loss)) if gross_loss != 0 else (gross_profit if gross_profit > 0 else 0.0)
        max_drawdown = self._calculate_max_drawdown(profits)
        average_win = self._safe_div(gross_profit, winning_trades)
        average_loss = self._safe_div(gross_loss, losing_trades)

        rows = session.execute(
            select(
                Position.id,
                Position.account_id,
                Position.profit,
                Position.symbol_id,
                Signal.strategy_id,
                Signal.timeframe_id,
                Signal.entry_price,
                Signal.stop_loss,
                Signal.take_profit,
            )
            .join(ExecutionOrder, ExecutionOrder.id == Position.execution_order_id)
            .join(Signal, Signal.id == ExecutionOrder.signal_id)
            .where(and_(Position.status == "CLOSED", Position.closed_at >= day_start, Position.closed_at <= now))
        ).all()

        rr_values: list[float] = []
        for r in rows:
            entry = float(r.entry_price or 0.0)
            sl = float(r.stop_loss or 0.0)
            tp = float(r.take_profit or 0.0)
            risk = abs(entry - sl)
            reward = abs(tp - entry)
            if risk > 0:
                rr_values.append(reward / risk)
        average_rr = self._safe_div(sum(rr_values), len(rr_values))

        account_ids = {r.account_id for r in summary_rows if r.account_id is not None}
        for account_id in account_ids:
            self.performance_repository.upsert_performance_daily(
                account_id=account_id,
                trade_date=day_start.date(),
                gross_profit=gross_profit,
                gross_loss=gross_loss,
                net_profit=net_profit,
                win_rate=win_rate,
                total_trades=total_trades,
                max_drawdown=max_drawdown,
                details={
                    "winning_trades": winning_trades,
                    "losing_trades": losing_trades,
                    "average_win": average_win,
                    "average_loss": average_loss,
                    "average_rr": average_rr,
                },
            )

        # performance_by_strategy aggregation per strategy+symbol+timeframe
        grouped: dict[tuple[uuid.UUID, uuid.UUID, uuid.UUID], list[tuple[float, float]]] = defaultdict(list)
        for r in rows:
            key = (r.strategy_id, r.symbol_id, r.timeframe_id)
            entry = float(r.entry_price or 0.0)
            sl = float(r.stop_loss or 0.0)
            tp = float(r.take_profit or 0.0)
            rr = 0.0
            risk = abs(entry - sl)
            if risk > 0:
                rr = abs(tp - entry) / risk
            grouped[key].append((float(r.profit or 0.0), rr))

        for (strategy_id, symbol_id, timeframe_id), items in grouped.items():
            strategy_profits = [p for p, _ in items]
            strategy_wins = [p for p in strategy_profits if p > 0]
            strategy_losses = [p for p in strategy_profits if p < 0]

            total = len(strategy_profits)
            win_rate_s = self._safe_div(len(strategy_wins), total)
            gross_profit_s = sum(strategy_wins)
            gross_loss_s = sum(strategy_losses)
            net_profit_s = gross_profit_s + gross_loss_s
            profit_factor_s = self._safe_div(gross_profit_s, abs(gross_loss_s)) if gross_loss_s != 0 else (gross_profit_s if gross_profit_s > 0 else 0.0)

            avg_rr_s = self._safe_div(sum(rr for _, rr in items), len(items))

            self.performance_repository.create_performance_by_strategy(
                strategy_id=strategy_id,
                account_id=None,
                period_start=day_start.date(),
                period_end=now.date(),
                total_trades=total,
                win_rate=win_rate_s,
                net_profit=net_profit_s,
                profit_factor=profit_factor_s,
                details={
                    "symbol_id": str(symbol_id),
                    "timeframe_id": str(timeframe_id),
                    "gross_profit": gross_profit_s,
                    "gross_loss": gross_loss_s,
                    "average_rr": avg_rr_s,
                },
            )

        self.performance_repository.session.commit()

        return {
            "trade_date": day_start.date().isoformat(),
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": win_rate,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "net_profit": net_profit,
            "profit_factor": profit_factor,
            "max_drawdown": max_drawdown,
            "average_win": average_win,
            "average_loss": average_loss,
            "average_rr": average_rr,
        }
