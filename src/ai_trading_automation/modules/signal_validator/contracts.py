"""Contracts for signal validator module."""

from dataclasses import dataclass

from ai_trading_automation.modules.market_regime.models import MarketRegimeResult
from ai_trading_automation.modules.signal_contract.models import SignalContract


@dataclass(slots=True)
class SignalValidationRequest:
    """Input contract for validating standardized signal."""

    signal: SignalContract
    market_regime: MarketRegimeResult | None = None
    min_score: float = 60.0
