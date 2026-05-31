"""Acceptance checks for FastAPI dashboard backend."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.main import app


def main() -> None:
    client = TestClient(app)

    health_resp = client.get("/api/v1/health")
    health_ok = health_resp.status_code == 200 and health_resp.json().get("status") == "ok"

    bot_status_ok = client.get("/api/v1/bot/status").status_code == 200
    candles_ok = client.get("/api/v1/market/candles", params={"symbol": "XAUUSD", "timeframe": "M5", "limit": 50}).status_code == 200

    signals_ok = client.get("/api/v1/signals").status_code == 200
    orders_ok = client.get("/api/v1/execution/orders").status_code == 200
    positions_ok = client.get("/api/v1/positions/open").status_code == 200
    journals_ok = client.get("/api/v1/journals").status_code == 200

    activate_resp = client.post("/api/v1/bot/kill-switch/activate", json={"reason": "api-acceptance", "actor": "test"})
    deactivate_resp = client.post("/api/v1/bot/kill-switch/deactivate", json={"reason": "api-acceptance", "actor": "test"})
    kill_switch_ok = activate_resp.status_code == 200 and deactivate_resp.status_code == 200

    print("api_health_ok", health_ok)
    print("bot_status_read_ok", bot_status_ok)
    print("candles_read_ok", candles_ok)
    print("signals_orders_positions_journals_read_ok", all([signals_ok, orders_ok, positions_ok, journals_ok]))
    print("kill_switch_api_ok", kill_switch_ok)


if __name__ == "__main__":
    main()
