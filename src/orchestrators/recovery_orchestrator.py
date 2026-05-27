"""Recovery orchestrator for startup state restoration and safety checks."""

from __future__ import annotations

import uuid
from typing import Any

from loguru import logger

from src.repositories.safety_repository import SafetyRepository
from src.services.position_sync_service import PositionSyncService
from src.services.runtime_recovery_service import RuntimeRecoveryService
from src.services.runtime_state_service import RuntimeStateService


class RecoveryOrchestrator:
    """Recover runtime baseline before live cycle starts."""

    def __init__(
        self,
        runtime_state_service: RuntimeStateService | None = None,
        position_sync_service: PositionSyncService | None = None,
        safety_repository: SafetyRepository | None = None,
        account_id: uuid.UUID | None = None,
        runtime_recovery_service: RuntimeRecoveryService | None = None,
    ) -> None:
        self.runtime_state_service = runtime_state_service
        self.position_sync_service = position_sync_service
        self.safety_repository = safety_repository
        self.account_id = account_id
        self.runtime_recovery_service = runtime_recovery_service

    def restore_runtime_state(self) -> dict[str, Any]:
        if self.runtime_state_service is None:
            return {}
        return {
            "last_heartbeat_at": self.runtime_state_service.get_state("last_heartbeat_at"),
            "last_cycle_status": self.runtime_state_service.get_state("last_cycle_status"),
            "last_runtime_status": self.runtime_state_service.get_state("status"),
        }

    def sync_open_positions_on_startup(self) -> int:
        if self.position_sync_service is None or self.account_id is None:
            return 0
        positions = self.position_sync_service.sync_open_positions(account_id=self.account_id)
        return len(positions)

    def check_kill_switch_state(self) -> bool:
        if self.safety_repository is None:
            return False
        return self.safety_repository.get_active_kill_switch() is not None

    def run_startup(self) -> dict[str, Any]:
        if self.runtime_recovery_service is not None:
            result = self.runtime_recovery_service.run_startup_recovery()
            logger.info("Recovery startup result: {}", result)
            return result

        runtime_state = self.restore_runtime_state()
        synced_positions = self.sync_open_positions_on_startup()
        kill_switch_active = self.check_kill_switch_state()

        result = {
            "runtime_state": runtime_state,
            "synced_positions": synced_positions,
            "kill_switch_active": kill_switch_active,
        }
        logger.info("Recovery startup result: {}", result)
        return result
