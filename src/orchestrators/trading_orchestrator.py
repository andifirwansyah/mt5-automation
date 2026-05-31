"""Main orchestrator for sequential trading pipeline execution."""

from __future__ import annotations

from typing import Any, Protocol

from loguru import logger

from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext


class EngineAuditRunner(Protocol):
    """Protocol for engine audit execution service."""

    def run_and_audit(self, step: PipelineStep, context: TradingContext) -> TradingContext:
        ...


class RejectionJournalRunner(Protocol):
    def record_rejection(self, context: TradingContext, step_name: str) -> None:
        ...

    def record_fatal(self, context: TradingContext, step_name: str, error_message: str) -> None:
        ...


class TradingOrchestrator:
    """Execute trading cycle through all configured pipeline steps."""

    def __init__(
        self,
        steps: list[PipelineStep],
        engine_audit_service: EngineAuditRunner,
        journal_engine: Any | None = None,
        rejection_journal_service: RejectionJournalRunner | None = None,
    ) -> None:
        self.steps = steps
        self.engine_audit_service = engine_audit_service
        self.journal_engine = journal_engine
        self.rejection_journal_service = rejection_journal_service

    def _record_rejection(self, context: TradingContext, step_name: str) -> None:
        if not context.rejection_reason:
            context.reject("INVALID_REJECTION_REASON", {"message": "reject without rejection_reason is invalid"})

        if self.rejection_journal_service is not None:
            self.rejection_journal_service.record_rejection(context=context, step_name=step_name)
            return

        if self.journal_engine is None:
            return
        if hasattr(self.journal_engine, "record_rejection"):
            self.journal_engine.record_rejection(context)

    def _record_fatal(self, context: TradingContext, step_name: str, error_message: str) -> None:
        if self.rejection_journal_service is not None:
            self.rejection_journal_service.record_fatal(context=context, step_name=step_name, error_message=error_message)
            return

        if self.journal_engine is None:
            return
        if hasattr(self.journal_engine, "record_fatal"):
            self.journal_engine.record_fatal(context=context, step_name=step_name, error_message=error_message)

    def run_cycle(self, candle_event: dict[str, Any]) -> TradingContext:
        """Run one candle event through sequential pipeline."""

        context = TradingContext.from_candle_event(candle_event)

        for step in self.steps:
            try:
                context = self.engine_audit_service.run_and_audit(step=step, context=context)
            except Exception as exc:
                logger.exception("Fatal pipeline exception at step: {}", step.name)
                context.reject(
                    reason="PIPELINE_FATAL_ERROR",
                    details={"step": step.name, "error_message": str(exc)},
                )
                try:
                    self._record_fatal(context=context, step_name=step.name, error_message=str(exc))
                except Exception:
                    logger.exception("Failed to journal fatal pipeline event")
                break

            if context.rejected:
                logger.warning(
                    "Pipeline rejected at step={} reason={}",
                    step.name,
                    context.rejection_reason,
                )
                try:
                    self._record_rejection(context=context, step_name=step.name)
                except Exception:
                    logger.exception("Failed to journal rejection pipeline event")
                break

        return context
