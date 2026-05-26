"""Application service shell for API routes."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ai_trading_automation.config import AppSettings
from ai_trading_automation.core import (
    PipelineOrchestratorService,
    PipelineRunRequest,
    PipelineRunResult,
    build_pipeline_orchestrator_from_settings,
)

from .schemas import (
    HealthResponse,
    PipelineLastRunResponse,
    PipelineRunRequestBody,
    PipelineRunResponse,
    PipelineStatusResponse,
)


@dataclass(slots=True)
class ApiShellService:
    """Thin service adapter so route layer stays logic-light."""

    last_run_at: datetime | None = None
    last_decision: str | None = None
    last_run_result: PipelineRunResult | None = None
    orchestrator: PipelineOrchestratorService | None = None

    def __post_init__(self) -> None:
        if self.orchestrator is None:
            settings = AppSettings.from_env()
            if settings.strict_db_runtime:
                self.orchestrator = build_pipeline_orchestrator_from_settings(settings)
                return

            try:
                self.orchestrator = build_pipeline_orchestrator_from_settings(settings)
            except Exception:
                self.orchestrator = PipelineOrchestratorService()

    def get_health(self) -> HealthResponse:
        """Return service health response for API checks."""
        return HealthResponse(
            status="ok",
            service="ai-trading-automation-api",
            trading_mode="paper",
            live_trading_enabled=False,
            timestamp=datetime.now(tz=UTC),
        )

    def get_pipeline_status(self) -> PipelineStatusResponse:
        """Return pipeline status from last orchestrator run."""
        return PipelineStatusResponse(
            pipeline_state="READY" if self.last_run_at is not None else "IDLE",
            message="Pipeline orchestrator is available in paper mode.",
            last_run_at=self.last_run_at,
            last_decision=self.last_decision,
        )

    def run_pipeline(self, payload: PipelineRunRequestBody) -> PipelineRunResponse:
        """Run end-to-end pipeline in paper mode orchestration."""
        run_result = self.orchestrator.run(
            PipelineRunRequest(
                dataset_path=Path(payload.dataset_path),
                symbol=payload.symbol,
                timeframe=payload.timeframe,
                account_balance=payload.account_balance,
                requested_risk_percent=payload.requested_risk_percent,
                daily_realized_loss=payload.daily_realized_loss,
                open_positions_count=payload.open_positions_count,
                persist_performance_report=payload.persist_performance_report,
            )
        )
        self.last_run_at = run_result.run_at
        self.last_decision = run_result.decision
        self.last_run_result = run_result

        return PipelineRunResponse(
            accepted=run_result.success,
            message=run_result.message,
            stage=run_result.stage,
            decision=run_result.decision,
        )

    def get_last_run(self) -> PipelineLastRunResponse:
        """Return last pipeline run summary for observability."""
        if self.last_run_result is None:
            return PipelineLastRunResponse(available=False)

        return PipelineLastRunResponse(
            available=True,
            success=self.last_run_result.success,
            stage=self.last_run_result.stage,
            message=self.last_run_result.message,
            decision=self.last_run_result.decision,
            run_at=self.last_run_result.run_at,
            artifacts=self.last_run_result.artifacts,
        )
