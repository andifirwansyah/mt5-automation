"""Centralized service to persist pipeline rejection and fatal events."""

from __future__ import annotations

from src.pipeline.trading_context import TradingContext
from src.repositories.journal_repository import JournalRepository


class RejectionJournalService:
    """Ensure every pipeline rejection/fatal event is journaled to database."""

    def __init__(self, journal_repository: JournalRepository) -> None:
        self.journal_repository = journal_repository

    @staticmethod
    def _validate_rejection(context: TradingContext) -> None:
        if not context.rejected:
            raise ValueError("context is not rejected")
        if not context.rejection_reason:
            raise ValueError("reject without rejection_reason is invalid")

    def record_rejection(self, context: TradingContext, step_name: str) -> None:
        self._validate_rejection(context)
        self.journal_repository.create_trade_journal(
            journal_type="PIPELINE_REJECTION",
            message=f"Pipeline rejected at step={step_name} reason={context.rejection_reason}",
            trace_id=context.trace_id,
            details={
                "step": step_name,
                "rejection_reason": context.rejection_reason,
                "rejection_details": context.rejection_details or {},
            },
        )
        self.journal_repository.session.commit()

    def record_fatal(self, context: TradingContext, step_name: str, error_message: str) -> None:
        self.journal_repository.create_trade_journal(
            journal_type="PIPELINE_FATAL",
            message=f"Pipeline fatal at step={step_name}",
            trace_id=context.trace_id,
            details={
                "step": step_name,
                "error_message": error_message,
                "rejection_reason": context.rejection_reason,
                "rejection_details": context.rejection_details or {},
            },
        )
        self.journal_repository.session.commit()
