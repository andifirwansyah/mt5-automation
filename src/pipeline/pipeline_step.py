"""Pipeline step contract for sequential trading engines."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.pipeline.trading_context import TradingContext


class PipelineStep(ABC):
    """Base contract for all pipeline engines."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique step name used for audit trail."""

    @abstractmethod
    def run(self, context: TradingContext) -> TradingContext:
        """Execute step and return updated context."""
