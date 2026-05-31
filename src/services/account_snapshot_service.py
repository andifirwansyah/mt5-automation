"""Service for account snapshot persistence."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from src.infrastructure.database.models import AccountSnapshot
from src.repositories.account_repository import AccountRepository


class AccountSnapshotService:
    """Save account snapshots using repository layer."""

    def __init__(self, account_repository: AccountRepository) -> None:
        self.account_repository = account_repository

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    def save_account_snapshot(self, account_id: uuid.UUID, payload: dict[str, Any]) -> AccountSnapshot:
        snapshot = self.account_repository.create_account_snapshot(
            account_id=account_id,
            balance=float(payload.get("balance", 0.0)),
            equity=float(payload.get("equity", 0.0)),
            margin=float(payload.get("margin", 0.0)),
            free_margin=float(payload.get("free_margin", payload.get("margin_free", 0.0))),
            margin_level=float(payload.get("margin_level", 0.0)),
            profit=float(payload.get("profit", 0.0)),
            snapshot_time=payload.get("snapshot_time", self._utc_now()),
            raw_payload=payload,
        )
        self.account_repository.session.commit()
        return snapshot
