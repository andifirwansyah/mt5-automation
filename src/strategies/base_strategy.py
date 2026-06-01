"""Base strategy contract for pluggable signal generation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.domain.models.market_snapshot import MarketSnapshot
from src.domain.models.regime_result import RegimeResult
from src.domain.models.signal import RawSignal
from src.trading.technical_analysis.models import TechnicalAnalysisResult


class BaseStrategy(ABC):
    """Abstract base class for all signal strategies."""

    strategy_code: str

    @abstractmethod
    def generate_signal(
        self,
        market_snapshot: MarketSnapshot,
        regime: RegimeResult,
        config: dict[str, Any],
        technical_analysis: TechnicalAnalysisResult | None = None,
    ) -> RawSignal | None:
        """Generate signal from current market snapshot and regime."""
