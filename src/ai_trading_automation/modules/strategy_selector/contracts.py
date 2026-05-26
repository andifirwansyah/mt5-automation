"""Contracts for strategy selector module."""

from dataclasses import dataclass

from ai_trading_automation.modules.market_regime.models import MarketRegimeResult


@dataclass(slots=True)
class StrategySelectorRequest:
    """Input contract for strategy selection."""

    market_regime: MarketRegimeResult
    min_regime_confidence: float = 0.45
