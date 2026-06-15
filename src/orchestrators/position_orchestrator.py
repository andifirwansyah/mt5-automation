"""Position orchestrator for sync, snapshot, and lifecycle checks."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.repositories.position_repository import PositionRepository
from src.services.position_sync_service import PositionSyncService
from src.services.trade_lifecycle_service import TradeLifecycleService
from src.services.trade_management_service import TradeManagementService


class PositionOrchestrator:
    """Run periodic position synchronization cycle."""

    def __init__(
        self,
        position_sync_service: PositionSyncService,
        trade_lifecycle_service: TradeLifecycleService,
        position_repository: PositionRepository,
        trade_management_service: TradeManagementService | None = None,
    ) -> None:
        self.position_sync_service = position_sync_service
        self.trade_lifecycle_service = trade_lifecycle_service
        self.position_repository = position_repository
        self.trade_management_service = trade_management_service

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    def run_cycle(self, account_id: uuid.UUID) -> dict[str, int | list]:
        synced_positions = self.position_sync_service.sync_open_positions(account_id=account_id)

        managed = {"evaluated": 0, "modified": 0}
        if self.trade_management_service is not None:
            managed = self.trade_management_service.manage_positions(synced_positions)

        snapshots_created = 0
        for position in synced_positions:
            details = position.details or {}
            current_price = float(details.get("price_current", position.entry_price))
            unrealized_profit = float(details.get("profit", position.profit or 0.0))
            self.position_repository.create_position_snapshot(
                position_id=position.id,
                snapshot_time=self._utc_now(),
                current_price=current_price,
                unrealized_profit=unrealized_profit,
                swap=float(details.get("swap", 0.0)),
                commission=float(details.get("commission", 0.0)),
                raw_payload=details,
            )
            snapshots_created += 1

        lifecycle_result = self.trade_lifecycle_service.detect_order_position_lifecycle(account_id=account_id)
        self.position_repository.session.commit()

        return {
            "synced_positions": len(synced_positions),
            "snapshots_created": snapshots_created,
            "closed_positions": lifecycle_result.get("closed_positions_db", 0),
            "closed_position_rows": lifecycle_result.get("closed_positions", []),
            "sl_modified": managed.get("modified", 0),
        }
