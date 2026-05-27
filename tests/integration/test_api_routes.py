from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import app
from src.repositories.safety_repository import SafetyRepository
from src.infrastructure.database.session import SessionLocal


def test_fastapi_health_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"


def test_kill_switch_activate_deactivate_api() -> None:
    session = SessionLocal()
    try:
        repo = SafetyRepository(session)
        repo.deactivate_kill_switch(deactivated_by="test-pre-clean", details={"reason": "pre-clean"})
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    activate = client.post("/api/v1/bot/kill-switch/activate", json={"reason": "test", "actor": "pytest"})
    assert activate.status_code == 200
    assert "activated" in activate.json()["message"].lower()

    deactivate = client.post("/api/v1/bot/kill-switch/deactivate", json={"reason": "test done", "actor": "pytest"})
    assert deactivate.status_code == 200
    assert "deactivated" in deactivate.json()["message"].lower()
