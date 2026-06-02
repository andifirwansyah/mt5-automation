from __future__ import annotations

import uuid

from src.infrastructure.database.session import SessionLocal
from src.repositories.account_repository import AccountRepository
from src.services.account_snapshot_updater_service import AccountSnapshotUpdaterService


def test_account_snapshot_updater_saves_snapshot_outside_pipeline(db_session) -> None:
    account_repo = AccountRepository(db_session)
    account = account_repo.get_or_create_trading_account(
        account_number=f"pytest-{uuid.uuid4().hex[:10]}",
        account_name="Pytest Account",
        broker_server="Demo-Server",
        base_currency="USD",
        leverage=100,
        metadata={"source": "pytest"},
    )
    db_session.commit()

    class FakeAccountClient:
        @staticmethod
        def get_account_info() -> dict:
            return {
                "balance": 10123.45,
                "equity": 10140.00,
                "margin": 50.0,
                "margin_free": 10090.0,
                "margin_level": 2000.0,
                "profit": 16.55,
            }

    updater = AccountSnapshotUpdaterService(
        session_factory=SessionLocal,
        account_client=FakeAccountClient(),
        account_id=account.id,
        interval_seconds=0.1,
    )

    saved = updater.sync_once()
    verify_session = SessionLocal()
    try:
        latest = AccountRepository(verify_session).get_latest_account_snapshot(account.id)
    finally:
        verify_session.close()

    assert saved is True
    assert latest is not None
    assert float(latest.balance) == 10123.45
    assert float(latest.equity) == 10140.0
    assert float(latest.free_margin) == 10090.0
