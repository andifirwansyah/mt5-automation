from pathlib import Path
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from ai_trading_automation.api import create_app


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


def test_health_endpoint_available() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["trading_mode"] == "paper"
    assert body["live_trading_enabled"] is False


def test_pipeline_run_endpoint_executes_orchestrator(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    _write_dataset_csv(dataset_root=dataset_root, timeframe="H1")

    client = TestClient(create_app())

    response = client.post(
        "/pipeline/run",
        json={
            "dataset_path": str(dataset_root),
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "account_balance": 10000,
            "requested_risk_percent": 0.5,
            "daily_realized_loss": 0.0,
            "open_positions_count": 0,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["stage"] == "completed"


def test_pipeline_status_updates_after_run(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    _write_dataset_csv(dataset_root=dataset_root, timeframe="H1")

    client = TestClient(create_app())
    client.post(
        "/pipeline/run",
        json={
            "dataset_path": str(dataset_root),
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "account_balance": 10000,
        },
    )

    status_response = client.get("/pipeline/status")
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["pipeline_state"] == "READY"
    assert status_body["last_run_at"] is not None


def test_pipeline_last_run_endpoint(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    _write_dataset_csv(dataset_root=dataset_root, timeframe="H1")

    client = TestClient(create_app())

    before = client.get("/pipeline/last-run")
    assert before.status_code == 200
    assert before.json()["available"] is False

    client.post(
        "/pipeline/run",
        json={
            "dataset_path": str(dataset_root),
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "account_balance": 10000,
        },
    )

    after = client.get("/pipeline/last-run")
    assert after.status_code == 200
    body = after.json()
    assert body["available"] is True
    assert body["stage"] == "completed"
    assert body["run_at"] is not None


def test_live_execution_endpoint_not_exposed() -> None:
    client = TestClient(create_app())

    response = client.post("/execution/live")

    assert response.status_code == 404
