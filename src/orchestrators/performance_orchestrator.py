"""Performance orchestrator for analytics and strategy feedback loop."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from loguru import logger


class PerformanceOrchestrator:
    """Run periodic performance analytics and feedback cycle."""

    def __init__(self, performance_analyzer: Any, strategy_feedback_loop: Any) -> None:
        self.performance_analyzer = performance_analyzer
        self.strategy_feedback_loop = strategy_feedback_loop
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @staticmethod
    def _run_component(component: Any) -> Any:
        if hasattr(component, "run_cycle"):
            return component.run_cycle()
        if hasattr(component, "run"):
            return component.run()
        if callable(component):
            return component()
        return None

    def run_cycle(self) -> dict[str, Any]:
        analyzer_result = self._run_component(self.performance_analyzer)
        feedback_result = self._run_component(self.strategy_feedback_loop)
        return {
            "run_at": datetime.now(timezone.utc).isoformat(),
            "performance_analyzer": analyzer_result,
            "strategy_feedback": feedback_result,
        }

    def start(self, interval_seconds: float = 300.0) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()

        def _loop() -> None:
            while not self._stop_event.is_set():
                try:
                    self.run_cycle()
                except Exception:
                    logger.exception("Performance orchestrator cycle failed")
                self._stop_event.wait(interval_seconds)

        self._thread = threading.Thread(target=_loop, name="performance-orchestrator", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
