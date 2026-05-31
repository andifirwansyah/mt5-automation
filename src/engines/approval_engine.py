"""Approval engine for manual approval workflow stub."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.config.settings import AppSettings, get_settings
from src.domain.enums import ValidationStatus
from src.domain.models.validation_result import ValidationResult
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories.execution_repository import ExecutionRepository


class ApprovalEngine(PipelineStep):
    """Handles optional manual approval request before execution."""

    @property
    def name(self) -> str:
        return "ApprovalEngine"

    def __init__(self, execution_repository: ExecutionRepository, settings: AppSettings | None = None) -> None:
        self.execution_repository = execution_repository
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
        if context.execution_decision is None:
            context.reject("APPROVAL_FAILED", {"message": "execution_decision missing"})
            return context

        if not bool(self.settings.approval_required):
            context.approval_result = ValidationResult(
                status=ValidationStatus.PASSED,
                reason=None,
                validator_name="ApprovalEngine",
                details={"message": "Approval skipped (approval_required=false)"},
            )
            return context

        if context.execution_decision.status.value != "REQUIRE_MANUAL_APPROVAL":
            context.approval_result = ValidationResult(
                status=ValidationStatus.PASSED,
                reason=None,
                validator_name="ApprovalEngine",
                details={"message": "No manual approval required by decision"},
            )
            return context

        decision_id = self._as_uuid((context.execution_decision.details or {}).get("execution_decision_id"))
        if decision_id is None:
            context.reject("APPROVAL_FAILED", {"message": "execution_decision_id missing"})
            return context

        self.execution_repository.create_approval_request(
            execution_decision_id=decision_id,
            approval_required=True,
            status="PENDING",
            requested_at=datetime.now(timezone.utc),
            requested_by="system",
            details={"trace_id": str(context.trace_id)},
        )
        self.execution_repository.session.commit()

        context.approval_result = ValidationResult(
            status=ValidationStatus.REJECTED,
            reason="APPROVAL_PENDING",
            validator_name="ApprovalEngine",
            details={"message": "Manual approval required and pending"},
        )
        context.reject("APPROVAL_PENDING", context.approval_result.details)
        return context
