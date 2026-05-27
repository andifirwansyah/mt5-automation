"""Service to execute pipeline step with audit trail logging."""

from __future__ import annotations

import time
import uuid

from loguru import logger

from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories.bot_repository import BotRepository


class EngineAuditService:
    """Run pipeline steps and persist engine run audit records."""

    def __init__(self, bot_repository: BotRepository, bot_instance_id: uuid.UUID | None = None) -> None:
        self.bot_repository = bot_repository
        self.bot_instance_id = bot_instance_id

    def run_and_audit(self, step: PipelineStep, context: TradingContext) -> TradingContext:
        started = time.perf_counter()

        self.bot_repository.create_engine_run(
            bot_instance_id=self.bot_instance_id,
            trace_id=context.trace_id,
            engine_name=step.name,
            status="RUNNING",
            input_reference={
                "symbol": context.symbol,
                "timeframe": context.timeframe,
                "candle_time": context.candle_time.isoformat(),
            },
            output_reference={},
        )
        self.bot_repository.session.commit()

        try:
            updated_context = step.run(context)
            duration_ms = int((time.perf_counter() - started) * 1000)

            status = "REJECTED" if updated_context.rejected else "SUCCESS"
            self.bot_repository.create_engine_run(
                bot_instance_id=self.bot_instance_id,
                trace_id=updated_context.trace_id,
                engine_name=step.name,
                status=status,
                input_reference={"trace_id": str(updated_context.trace_id)},
                output_reference={
                    "rejected": updated_context.rejected,
                    "rejection_reason": updated_context.rejection_reason,
                },
                duration_ms=duration_ms,
            )
            self.bot_repository.session.commit()
            return updated_context
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            self.bot_repository.create_engine_run(
                bot_instance_id=self.bot_instance_id,
                trace_id=context.trace_id,
                engine_name=step.name,
                status="FAILED",
                input_reference={"trace_id": str(context.trace_id)},
                output_reference={},
                duration_ms=duration_ms,
                error_message=str(exc),
            )
            self.bot_repository.session.commit()
            logger.exception("Engine step failed: {}", step.name)
            raise
