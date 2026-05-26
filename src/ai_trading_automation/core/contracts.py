"""Contracts for core pipeline orchestrator."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class PipelineRunRequest:
    """Input contract for end-to-end pipeline run."""

    dataset_path: Path
    symbol: str
    timeframe: str
    account_balance: float
    requested_risk_percent: float = 0.5
    daily_realized_loss: float = 0.0
    open_positions_count: int = 0
    persist_performance_report: bool = False
