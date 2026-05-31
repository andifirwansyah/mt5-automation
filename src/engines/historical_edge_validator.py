"""Historical edge validator engine."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from src.config.settings import AppSettings, get_settings
from src.domain.models.edge_result import EdgeResult
from src.infrastructure.database.models import ExecutionOrder, PerformanceByStrategy, Position, Signal
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories.signal_repository import SignalRepository


class HistoricalEdgeValidator(PipelineStep):
    """Validate signal against historical strategy edge."""

    @property
    def name(self) -> str:
        return "HistoricalEdgeValidator"

    def __init__(self, signal_repository: SignalRepository, settings: AppSettings | None = None) -> None:
        self.signal_repository = signal_repository
        self.settings = settings or get_settings()

    @staticmethod
    def _as_uuid(value: object) -> uuid.UUID | None:
        if isinstance(value, uuid.UUID):
            return value
        if isinstance(value, str) and value:
            try:
                return uuid.UUID(value)
            except ValueError:
                return None
        return None

    def run(self, context: TradingContext) -> TradingContext:
        if context.signal_contract is None:
            context.reject("HISTORICAL_EDGE_FAILED", {"message": "signal_contract missing"})
            return context

        ingestion = context.ingestion_result or {}
        signal_id = self._as_uuid(context.signal_contract.metadata.get("signal_id"))
        symbol_id = self._as_uuid(ingestion.get("symbol_id"))
        timeframe_id = self._as_uuid((ingestion.get("timeframe_ids") or {}).get(context.timeframe))
        strategy_id = self._as_uuid((context.strategy_selection.details or {}).get("strategy_id") if context.strategy_selection else None)

        if signal_id is None or symbol_id is None or timeframe_id is None or strategy_id is None:
            context.reject("HISTORICAL_EDGE_FAILED", {"message": "signal/symbol/timeframe/strategy references missing"})
            return context

        session = self.signal_repository.session
        rows = session.execute(
            select(Position.profit, Signal.entry_price, Signal.stop_loss, Signal.take_profit)
            .join(ExecutionOrder, ExecutionOrder.id == Position.execution_order_id)
            .join(Signal, Signal.id == ExecutionOrder.signal_id)
            .where(
                Signal.strategy_id == strategy_id,
                Signal.symbol_id == symbol_id,
                Signal.timeframe_id == timeframe_id,
                Position.status == "CLOSED",
            )
        ).all()

        sample_size = len(rows)
        if sample_size == 0:
            win_rate = 0.0
            profit_factor = 0.0
            avg_rr = 0.0
            expectancy = 0.0
        else:
            profits = [float(r[0] or 0.0) for r in rows]
            wins = [p for p in profits if p > 0]
            losses = [p for p in profits if p < 0]

            win_rate = len(wins) / sample_size
            gross_profit = sum(wins)
            gross_loss_abs = abs(sum(losses))
            profit_factor = gross_profit / gross_loss_abs if gross_loss_abs > 0 else (gross_profit if gross_profit > 0 else 0.0)
            expectancy = sum(profits) / sample_size

            rr_values: list[float] = []
            for _, entry, sl, tp in rows:
                entry_v = float(entry or 0.0)
                sl_v = float(sl or 0.0)
                tp_v = float(tp or 0.0)
                risk = abs(entry_v - sl_v)
                reward = abs(tp_v - entry_v)
                if risk > 0:
                    rr_values.append(reward / risk)
            avg_rr = (sum(rr_values) / len(rr_values)) if rr_values else 0.0

        min_sample = int(self.settings.min_edge_sample_size)
        allow_low_sample = bool(self.settings.allow_low_sample_edge)
        min_win_rate = float(self.settings.edge_min_win_rate)
        min_profit_factor = float(self.settings.edge_min_profit_factor)

        if sample_size < min_sample:
            passed = allow_low_sample
            reason = "LOW_SAMPLE_ALLOWED" if allow_low_sample else "LOW_SAMPLE_REJECTED"
        else:
            passed = (win_rate >= min_win_rate) and (profit_factor >= min_profit_factor)
            reason = "EDGE_PASSED" if passed else "EDGE_THRESHOLD_FAILED"

        perf_row = session.execute(
            select(PerformanceByStrategy)
            .where(PerformanceByStrategy.strategy_id == strategy_id)
            .order_by(PerformanceByStrategy.period_end.desc())
            .limit(1)
        ).scalar_one_or_none()

        details = {
            "sample_size": sample_size,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "avg_rr": avg_rr,
            "expectancy": expectancy,
            "min_sample": min_sample,
            "allow_low_sample_edge": allow_low_sample,
            "edge_min_win_rate": min_win_rate,
            "edge_min_profit_factor": min_profit_factor,
            "performance_reference": {
                "period_start": perf_row.period_start.isoformat() if perf_row else None,
                "period_end": perf_row.period_end.isoformat() if perf_row else None,
                "net_profit": float(perf_row.net_profit) if perf_row else None,
            },
        }

        self.signal_repository.create_historical_edge_validation(
            signal_id=signal_id,
            strategy_id=strategy_id,
            sample_size=sample_size,
            win_rate=win_rate,
            expectancy=expectancy,
            passed=passed,
            validated_at=context.candle_time,
            details=details,
        )
        self.signal_repository.session.commit()

        context.historical_edge = EdgeResult(
            passed=passed,
            sample_size=sample_size,
            win_rate=win_rate,
            expectancy=expectancy,
            reason=reason,
            details=details,
        )

        if not passed:
            context.reject("HISTORICAL_EDGE_FAILED", details)
        return context
