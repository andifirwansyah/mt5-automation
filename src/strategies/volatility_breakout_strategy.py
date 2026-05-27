"""Volatility breakout strategy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.domain.enums import MarketRegimeType, SignalDirection
from src.domain.models.market_snapshot import MarketSnapshot
from src.domain.models.regime_result import RegimeResult
from src.domain.models.signal import RawSignal
from src.strategies.base_strategy import BaseStrategy


class VolatilityBreakoutStrategy(BaseStrategy):
    """Breakout strategy for high volatility condition."""

    strategy_code = "VOLATILITY_BREAKOUT"

    def generate_signal(self, market_snapshot: MarketSnapshot, regime: RegimeResult, config: dict[str, Any]) -> RawSignal | None:
        if regime.regime != MarketRegimeType.HIGH_VOLATILITY:
            return None

        atr = float(regime.features.get("atr", max(market_snapshot.high_price - market_snapshot.low_price, 0.01)))
        breakout_buffer = float(config.get("breakout_buffer_atr", 0.15)) * atr
        sl_mult = float(config.get("sl_atr_multiplier", 1.2))
        tp_mult = float(config.get("tp_atr_multiplier", 2.2))

        entry = market_snapshot.close_price
        upper_trigger = market_snapshot.high_price - breakout_buffer
        lower_trigger = market_snapshot.low_price + breakout_buffer

        if entry >= upper_trigger:
            direction = SignalDirection.BUY
            stop_loss = entry - (sl_mult * atr)
            take_profit = entry + (tp_mult * atr)
        elif entry <= lower_trigger:
            direction = SignalDirection.SELL
            stop_loss = entry + (sl_mult * atr)
            take_profit = entry - (tp_mult * atr)
        else:
            return None

        confidence = min(0.95, max(0.55, float(regime.features.get("volatility_score", 0.0)) * 10))
        return RawSignal(
            direction=direction,
            confidence=confidence,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            generated_at=datetime.now(timezone.utc),
            features={"atr": atr, "breakout_buffer": breakout_buffer},
            metadata={"strategy_code": self.strategy_code},
        )
