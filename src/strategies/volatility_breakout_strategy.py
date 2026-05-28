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
        prev_range_high = regime.features.get("prev_range_high")
        prev_range_low = regime.features.get("prev_range_low")
        if prev_range_high is None or prev_range_low is None:
            return None

        prev_range_high = float(prev_range_high)
        prev_range_low = float(prev_range_low)
        if prev_range_high <= prev_range_low:
            return None

        min_breakout_range_atr = float(config.get("min_breakout_range_atr", 1.0))
        if (prev_range_high - prev_range_low) < (min_breakout_range_atr * atr):
            return None

        breakout_buffer = float(config.get("breakout_buffer_atr", 0.15)) * atr
        min_body_atr = float(config.get("breakout_min_body_atr", 0.25))
        body_atr_ratio = float(regime.features.get("body_atr_ratio", 0.0))
        if body_atr_ratio < min_body_atr:
            return None

        require_close_break = bool(config.get("breakout_confirm_close", True))
        sl_mult = float(config.get("sl_atr_multiplier", 1.2))
        tp_mult = float(config.get("tp_atr_multiplier", 2.2))

        entry = market_snapshot.close_price
        upper_trigger = prev_range_high + breakout_buffer
        lower_trigger = prev_range_low - breakout_buffer

        bullish_break = entry >= upper_trigger if require_close_break else market_snapshot.high_price >= upper_trigger
        bearish_break = entry <= lower_trigger if require_close_break else market_snapshot.low_price <= lower_trigger

        if bullish_break:
            direction = SignalDirection.BUY
            stop_loss = entry - (sl_mult * atr)
            take_profit = entry + (tp_mult * atr)
        elif bearish_break:
            direction = SignalDirection.SELL
            stop_loss = entry + (sl_mult * atr)
            take_profit = entry - (tp_mult * atr)
        else:
            return None

        confidence = min(0.95, max(0.55, float(regime.features.get("volatility_score", 0.0)) * 8 + (body_atr_ratio * 0.2)))
        return RawSignal(
            direction=direction,
            confidence=confidence,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            generated_at=datetime.now(timezone.utc),
            features={
                "atr": atr,
                "breakout_buffer": breakout_buffer,
                "prev_range_high": prev_range_high,
                "prev_range_low": prev_range_low,
                "body_atr_ratio": body_atr_ratio,
            },
            metadata={"strategy_code": self.strategy_code},
        )
