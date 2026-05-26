"""Bootstrap helpers for runtime service composition."""

from ai_trading_automation.config import AppSettings
from ai_trading_automation.modules.paper_execution import PaperExecutionService, PaperOrderRepository
from ai_trading_automation.modules.trade_journal import TradeJournalRepository, TradeJournalService

from .database import create_db_engine, create_session_factory
from .service import PipelineOrchestratorService


def build_pipeline_orchestrator_from_settings(
    settings: AppSettings | None = None,
) -> PipelineOrchestratorService:
    """Build orchestrator with storage backends derived from settings/env."""
    active_settings = settings or AppSettings.from_env()

    db_engine = create_db_engine(active_settings)
    session_factory = create_session_factory(db_engine)

    trade_journal_service: TradeJournalService
    if active_settings.trade_journal_backend == "db":
        journal_repo = TradeJournalRepository(session_factory=session_factory)
        journal_repo.create_tables()
        trade_journal_service = TradeJournalService(storage_backend="db", repository=journal_repo)
    else:
        trade_journal_service = TradeJournalService(storage_backend="file")

    paper_execution_service: PaperExecutionService
    if active_settings.paper_execution_backend == "db":
        paper_repo = PaperOrderRepository(session_factory=session_factory)
        paper_repo.create_tables()
        paper_execution_service = PaperExecutionService(storage_backend="db", repository=paper_repo)
    else:
        paper_execution_service = PaperExecutionService(storage_backend="memory")

    return PipelineOrchestratorService(
        trade_journal_service=trade_journal_service,
        paper_execution_service=paper_execution_service,
    )
