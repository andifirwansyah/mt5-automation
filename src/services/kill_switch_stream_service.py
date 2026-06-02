"""Services for realtime kill-switch WebSocket streaming."""

from __future__ import annotations

from src.api.deps import model_to_dict
from src.repositories.safety_repository import SafetyRepository


class KillSwitchStreamService:
    """Load current kill-switch state for realtime dashboard updates."""

    def __init__(self, safety_repository: SafetyRepository) -> None:
        self.safety_repository = safety_repository

    def load_snapshot_status(self) -> dict[str, object | None]:
        return self._build_status(include_latest_inactive_state=False)

    def load_current_status(self) -> dict[str, object | None]:
        return self._build_status(include_latest_inactive_state=True)

    def _build_status(self, *, include_latest_inactive_state: bool) -> dict[str, object | None]:
        latest_state = self.safety_repository.get_latest_kill_switch_state()
        active_state = self.safety_repository.get_active_kill_switch()

        if latest_state is None:
            return {
                "is_active": False,
                "kill_switch": None,
            }

        kill_switch_payload = None
        if active_state is not None:
            kill_switch_payload = model_to_dict(active_state)
        elif include_latest_inactive_state:
            kill_switch_payload = model_to_dict(latest_state)
            kill_switch_payload["is_active"] = False

        return {
            "is_active": active_state is not None,
            "kill_switch": kill_switch_payload,
        }
