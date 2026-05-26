"""Contracts for strategy engine shell."""

from dataclasses import dataclass

from ai_trading_automation.modules.ohlcv_validation.models import ValidatedOHLCVFrame
from ai_trading_automation.modules.strategy_selector.models import SelectedStrategy


@dataclass(slots=True)
class StrategyEngineRequest:
    """Input contract for strategy execution shell."""

    selected_strategy: SelectedStrategy
    market_frame: ValidatedOHLCVFrame
