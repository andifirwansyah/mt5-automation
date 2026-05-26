"""Service layer for evidence-based performance analysis."""

from dataclasses import asdict
from datetime import UTC, datetime
import json

from .contracts import PerformanceAnalysisRequest
from .errors import PerformanceAnalyzerInputError
from .models import PerformanceReport


class PerformanceAnalyzerService:
    """Calculate baseline metrics from trade journal entries."""

    def analyze(self, request: PerformanceAnalysisRequest) -> PerformanceReport:
        """Compute win rate, avg R, drawdown, and rejection stats."""
        if request.entries is None:
            raise PerformanceAnalyzerInputError("entries must be provided.")

        entries = request.entries
        total_entries = len(entries)
        rejection_count = 0

        closed_trade_pnls: list[float] = []
        r_multiples: list[float] = []
        equity_curve: list[float] = []
        cumulative_pnl = 0.0

        for entry in entries:
            decision = str(entry.execution_decision.get("decision", "UNKNOWN"))
            if decision == "REJECT":
                rejection_count += 1

            result = entry.result or {}
            status = str(result.get("status", "UNKNOWN"))
            realized_pnl_raw = result.get("realized_pnl")
            if status != "CLOSED" or realized_pnl_raw is None:
                continue

            realized_pnl = float(realized_pnl_raw)
            closed_trade_pnls.append(realized_pnl)
            cumulative_pnl += realized_pnl
            equity_curve.append(cumulative_pnl)

            max_loss = float(entry.risk_plan.get("max_loss", 0.0) or 0.0)
            if max_loss > 0:
                r_multiples.append(realized_pnl / max_loss)

        closed_trades = len(closed_trade_pnls)
        wins = sum(1 for pnl in closed_trade_pnls if pnl > 0)
        losses = sum(1 for pnl in closed_trade_pnls if pnl < 0)
        total_trades = closed_trades

        win_rate = (wins / closed_trades * 100.0) if closed_trades > 0 else 0.0
        avg_r = (sum(r_multiples) / len(r_multiples)) if r_multiples else 0.0
        max_drawdown = self._calculate_max_drawdown(equity_curve)
        rejection_rate = (rejection_count / total_entries * 100.0) if total_entries > 0 else 0.0

        notes = [
            "Metrics are descriptive evidence only, not profitability claims.",
            "Use backtest and forward-test evidence before making performance conclusions.",
        ]
        if total_entries == 0:
            notes.append("Journal is empty; report contains zeroed baseline metrics.")

        report = PerformanceReport(
            total_entries=total_entries,
            total_trades=total_trades,
            closed_trades=closed_trades,
            wins=wins,
            losses=losses,
            win_rate=round(win_rate, 4),
            avg_r=round(avg_r, 6),
            max_drawdown=round(max_drawdown, 6),
            rejection_count=rejection_count,
            rejection_rate=round(rejection_rate, 4),
            notes=notes,
            generated_at=datetime.now(tz=UTC),
        )

        if request.persist_report:
            self._persist_report(report=report, output_path=request.report_path)

        return report

    def _calculate_max_drawdown(self, equity_curve: list[float]) -> float:
        if not equity_curve:
            return 0.0

        peak = equity_curve[0]
        max_drawdown = 0.0
        for value in equity_curve:
            if value > peak:
                peak = value
            drawdown = peak - value
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        return max_drawdown

    def _persist_report(self, report: PerformanceReport, output_path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(report)
        payload["generated_at"] = report.generated_at.isoformat() if report.generated_at else None
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
