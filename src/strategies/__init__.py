"""Strategy package for pluggable trading strategies."""

from src.strategies.base_strategy import BaseStrategy
from src.strategies.ema_atr_trend_strategy import EmaAtrTrendStrategy
from src.strategies.range_reversion_strategy import RangeReversionStrategy
from src.strategies.volatility_breakout_strategy import VolatilityBreakoutStrategy

__all__ = [
    "BaseStrategy",
    "EmaAtrTrendStrategy",
    "VolatilityBreakoutStrategy",
    "RangeReversionStrategy",
]
