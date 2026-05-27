"""Trade journal engine for auditable pipeline lifecycle records."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories.journal_repository import JournalRepository


class TradeJournalEngine(PipelineStep):
    """Persist important trading lifecycle events into trade_journals."""

    @property
    def name(self) -> str:
        return "TradeJournalEngine"

    def __init__(self, journal_repository: JournalRepository) -> None:
        self.journal_repository = journal_repository

    def _to_json_safe(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(k): self._to_json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._to_json_safe(v) for v in value]
        if is_dataclass(value):
            return self._to_json_safe(asdict(value))
        return str(value)

    def run(self, context: TradingContext) -> TradingContext:
        full_context = self._to_json_safe(asdict(context))

        if context.rejected:
            self.journal_repository.create_trade_journal(
                journal_type="SIGNAL_REJECTION",
                message=f"Pipeline rejected: {context.rejection_reason}",
                trace_id=context.trace_id,
                details={
                    "rejection_reason": context.rejection_reason,
                    "rejection_details": self._to_json_safe(context.rejection_details or {}),
                    "full_context": full_context,
                },
            )

        if context.execution_decision is not None:
            self.journal_repository.create_trade_journal(
                journal_type="EXECUTION_DECISION",
                message=f"Execution decision: {context.execution_decision.status.value}",
                trace_id=context.trace_id,
                details={
                    "decision": context.execution_decision.status.value,
                    "reason": context.execution_decision.reason,
                    "details": self._to_json_safe(context.execution_decision.details),
                    "full_context": full_context,
                },
            )

        if context.order_result is not None:
            self.journal_repository.create_trade_journal(
                journal_type="ORDER_EXECUTION",
                message=f"Order status: {context.order_result.status.value}",
                trace_id=context.trace_id,
                details={
                    "order_status": context.order_result.status.value,
                    "order_ticket": context.order_result.order_ticket,
                    "error_message": context.order_result.error_message,
                    "request_payload": self._to_json_safe(context.order_result.request_payload),
                    "response_payload": self._to_json_safe(context.order_result.response_payload),
                    "full_context": full_context,
                },
            )

        closed_count = int(((context.ingestion_result or {}).get("position_monitor") or {}).get("closed_positions", 0))
        if closed_count > 0:
            self.journal_repository.create_trade_journal(
                journal_type="CLOSED_TRADE",
                message=f"Detected {closed_count} closed positions",
                trace_id=context.trace_id,
                details={"closed_positions": closed_count, "full_context": full_context},
            )

        self.journal_repository.session.commit()
        return context
