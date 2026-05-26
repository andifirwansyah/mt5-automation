from datetime import UTC, datetime

from ai_trading_automation.modules.performance_analyzer import (
    PerformanceAnalysisRequest,
    PerformanceAnalyzerService,
)
from ai_trading_automation.modules.trade_journal.models import TradeJournalEntry


def _journal_entry(
    journal_id: str,
    decision: str,
    realized_pnl: float | None,
    status: str,
    max_loss: float = 100.0,
) -> TradeJournalEntry:
    return TradeJournalEntry(
        journal_id=journal_id,
        signal={"signal_id": f"sig-{journal_id}"} if decision != "REJECT" else None,
        signal_validation={"is_valid": decision != "REJECT"},
        risk_plan={"max_loss": max_loss},
        simulation_result={"passed": decision != "REJECT"},
        execution_decision={"decision": decision, "reason": "test"},
        order_state={"status": "OPEN"} if decision == "APPROVE" else None,
        result={"status": status, "realized_pnl": realized_pnl} if status else None,
        notes=[],
        created_at=datetime.now(tz=UTC),
        closed_at=datetime.now(tz=UTC) if status == "CLOSED" else None,
    )


def test_empty_journal_returns_zero_metrics() -> None:
    service = PerformanceAnalyzerService()

    report = service.analyze(PerformanceAnalysisRequest(entries=[]))

    assert report.total_entries == 0
    assert report.total_trades == 0
    assert report.win_rate == 0.0
    assert report.avg_r == 0.0
    assert report.max_drawdown == 0.0


def test_win_loss_sample_metrics() -> None:
    service = PerformanceAnalyzerService()
    entries = [
        _journal_entry("1", decision="APPROVE", realized_pnl=100.0, status="CLOSED"),
        _journal_entry("2", decision="APPROVE", realized_pnl=-50.0, status="CLOSED"),
        _journal_entry("3", decision="APPROVE", realized_pnl=200.0, status="CLOSED"),
    ]

    report = service.analyze(PerformanceAnalysisRequest(entries=entries))

    assert report.closed_trades == 3
    assert report.wins == 2
    assert report.losses == 1
    assert report.win_rate == 66.6667
    assert report.avg_r == 0.833333
    assert report.max_drawdown == 50.0


def test_rejected_stats_counted() -> None:
    service = PerformanceAnalyzerService()
    entries = [
        _journal_entry("1", decision="REJECT", realized_pnl=None, status=""),
        _journal_entry("2", decision="APPROVE", realized_pnl=20.0, status="CLOSED"),
        _journal_entry("3", decision="REJECT", realized_pnl=None, status=""),
        _journal_entry("4", decision="WAIT", realized_pnl=None, status=""),
    ]

    report = service.analyze(PerformanceAnalysisRequest(entries=entries))

    assert report.total_entries == 4
    assert report.rejection_count == 2
    assert report.rejection_rate == 50.0
