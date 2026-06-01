"""Trading pipeline builder for sequential engine order."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.pipeline.pipeline_step import PipelineStep


PIPELINE_STEP_ORDER: tuple[str, ...] = (
    "KillSwitchMonitor",
    "DataCollectorEngine",
    "MarketDataIngestionEngine",
    "DataQualityGuard",
    "MarketEventFilter",
    "MarketRegimeEngine",
    "TechnicalAnalysisEngine",
    "StrategySelector",
    "StrategyEngine",
    "SignalContractBuilder",
    "SignalValidator",
    "HistoricalEdgeValidator",
    "RiskEngine",
    "PreTradeSimulation",
    "BrokerHealthCheck",
    "ExecutionGate",
    "ApprovalEngine",
    "ExecutionEngine",
    "TradeJournalEngine",
    "RuntimeStateUpdater",
)


def _resolve_step(dependencies: Mapping[str, Any] | Any, key: str) -> PipelineStep:
    step = dependencies.get(key) if isinstance(dependencies, Mapping) else getattr(dependencies, key, None)
    if step is None:
        raise ValueError(f"Pipeline dependency not found for step: {key}")
    if not isinstance(step, PipelineStep):
        raise TypeError(f"Dependency '{key}' must implement PipelineStep")
    return step


def build_trading_pipeline(dependencies: Mapping[str, Any] | Any) -> list[PipelineStep]:
    """Build ordered sequential trading pipeline steps."""

    return [_resolve_step(dependencies, key) for key in PIPELINE_STEP_ORDER]
