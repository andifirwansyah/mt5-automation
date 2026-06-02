"""Background service to persist account snapshots independently of trading pipeline."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Callable

from loguru import logger
from sqlalchemy.orm import Session

from src.infrastructure.mt5.mt5_account import MT5AccountClient
from src.repositories.account_repository import AccountRepository
from src.services.account_snapshot_service import AccountSnapshotService


class AccountSnapshotUpdaterService:
    """Keep account snapshots fresh even when trading pipeline is blocked."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        account_client: MT5AccountClient,
        account_id: uuid.UUID,
        interval_seconds: float = 5.0,
    ) -> None:
        self.session_factory = session_factory
        self.account_client = account_client
        self.account_id = account_id
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    def sync_once(self) -> bool:
        payload = self.account_client.get_account_info()
        if not payload:
            return False

        session = self.session_factory()
        try:
            account_repository = AccountRepository(session)
            snapshot_service = AccountSnapshotService(account_repository)
            snapshot_time = self._utc_now()
            snapshot_payload = {
                **payload,
                "snapshot_time": snapshot_time,
                "raw_payload": {
                    **payload,
                    "snapshot_time": snapshot_time.isoformat(),
                },
            }
            snapshot_service.save_account_snapshot(account_id=self.account_id, payload=snapshot_payload)
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.sync_once()
            except Exception:
                logger.exception("Account snapshot updater loop failed")

            self._stop_event.wait(self.interval_seconds)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="account-snapshot-updater", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
