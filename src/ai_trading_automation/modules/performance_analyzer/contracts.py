"""Contracts for performance analyzer module."""

from dataclasses import dataclass
from pathlib import Path

from ai_trading_automation.modules.trade_journal.models import TradeJournalEntry


@dataclass(slots=True)
class PerformanceAnalysisRequest:
    """Input payload for performance analysis."""

    entries: list[TradeJournalEntry]
    persist_report: bool = False
    report_path: Path = Path("outputs/reports/performance_report.json")
