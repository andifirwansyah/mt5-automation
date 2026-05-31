"""Position monitor engine for syncing and snapshotting MT5 positions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories.position_repository import PositionRepository
from src.services.position_sync_service import PositionSyncService
from src.services.trade_lifecycle_service import TradeLifecycleService


class PositionMonitor(PipelineStep):
    """Sync open positions, create snapshots, and detect closed positions."""

    @property
    def name(self) -> str:
        return "PositionMonitor"

    def __init__(
        self,
        position_sync_service: PositionSyncService,
        trade_lifecycle_service: TradeLifecycleService,
        position_repository: PositionRepository,
        account_id: uuid.UUID,
    ) -> None:
        self.position_sync_service = position_sync_service
        self.trade_lifecycle_service = trade_lifecycle_service
        self.position_repository = position_repository
        self.account_id = account_id

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    def run(self, context: TradingContext) -> TradingContext:
        synced = self.position_sync_service.sync_open_positions(account_id=self.account_id)

        snapshots_created = 0
        for pos in synced:
            details = pos.details or {}
            self.position_repository.create_position_snapshot(
                position_id=pos.id,
                snapshot_time=self._utc_now(),
                current_price=float(details.get("price_current", pos.entry_price)),
                unrealized_profit=float(details.get("profit", 0.0)),
                swap=float(details.get("swap", 0.0)),
                commission=float(details.get("commission", 0.0)),
                raw_payload=details,
            )
            snapshots_created += 1

        lifecycle_result = self.trade_lifecycle_service.detect_order_position_lifecycle(account_id=self.account_id)
        self.position_repository.session.commit()

        context.ingestion_result = {
            **(context.ingestion_result or {}),
            "position_monitor": {
                "synced_open_positions": len(synced),
                "snapshots_created": snapshots_created,
                "closed_positions": lifecycle_result.get("closed_positions_db", 0),
            },
        }
        return context
