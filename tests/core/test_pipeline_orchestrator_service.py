from pathlib import Path
from datetime import datetime, timedelta

from ai_trading_automation.core import PipelineOrchestratorService, PipelineRunRequest


def _write_dataset_csv(dataset_root: Path, timeframe: str = "H1", rows: int = 80) -> None:
    timeframe_dir = dataset_root / timeframe
    timeframe_dir.mkdir(parents=True, exist_ok=True)

    lines = ["Date,Open,High,Low,Close,Volume"]
    base = 2300.0
    start = datetime(2026, 1, 1, 0, 0, 0)
    for idx in range(rows):
        open_price = base + (idx * 0.4)
        close_price = open_price + 0.2
        high_price = close_price + 0.2
        low_price = open_price - 0.2
        timestamp = (start + timedelta(hours=idx)).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(
            f"{timestamp},{open_price:.4f},{high_price:.4f},{low_price:.4f},{close_price:.4f},{100+idx}"
        )

    (timeframe_dir / "xauusd_h1.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_pipeline_orchestrator_run_success(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    _write_dataset_csv(dataset_root=dataset_root, timeframe="H1")

    service = PipelineOrchestratorService()
    result = service.run(
        PipelineRunRequest(
            dataset_path=dataset_root,
            symbol="XAUUSD",
            timeframe="H1",
            account_balance=10000.0,
            requested_risk_percent=0.5,
            daily_realized_loss=0.0,
            open_positions_count=0,
        )
    )

    assert result.success is True
    assert result.stage == "completed"
    assert result.decision in {"APPROVE", "REDUCE_RISK", "WAIT", "REJECT"}
    assert "journal_id" in result.artifacts


def test_pipeline_orchestrator_fail_on_missing_timeframe(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    # Intentionally do not create H1 file/folder.
    dataset_root.mkdir(parents=True, exist_ok=True)

    service = PipelineOrchestratorService()
    result = service.run(
        PipelineRunRequest(
            dataset_path=dataset_root,
            symbol="XAUUSD",
            timeframe="H1",
            account_balance=10000.0,
        )
    )

    assert result.success is False
    assert result.stage == "market_data"
    assert "failed" in result.message.lower()
