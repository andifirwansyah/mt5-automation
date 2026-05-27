"""Range mean-reversion strategy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.domain.enums import MarketRegimeType, SignalDirection
from src.domain.models.market_snapshot import MarketSnapshot
from src.domain.models.regime_result import RegimeResult
from src.domain.models.signal import RawSignal
from src.strategies.base_strategy import BaseStrategy


class RangeReversionStrategy(BaseStrategy):
    """Mean reversion strategy for ranging markets."""

    strategy_code = "RANGE_REVERSION"

    def generate_signal(self, market_snapshot: MarketSnapshot, regime: RegimeResult, config: dict[str, Any]) -> RawSignal | None:
        if regime.regime != MarketRegimeType.RANGING:
            return None

        atr = float(regime.features.get("atr", max(market_snapshot.high_price - market_snapshot.low_price, 0.01)))
        mean_price = float(regime.features.get("ema_slow", (market_snapshot.high_price + market_snapshot.low_price) / 2))
        reversion_threshold = float(config.get("reversion_threshold_atr", 0.6)) * atr

        entry = market_snapshot.close_price
        deviation = entry - mean_price

        sl_mult = float(config.get("sl_atr_multiplier", 1.2))
        tp_mult = float(config.get("tp_atr_multiplier", 1.8))

        if deviation >= reversion_threshold:
            direction = SignalDirection.SELL
            stop_loss = entry + (sl_mult * atr)
            take_profit = entry - (tp_mult * atr)
        elif deviation <= -reversion_threshold:
            direction = SignalDirection.BUY
            stop_loss = entry - (sl_mult * atr)
            take_profit = entry + (tp_mult * atr)
        else:
            return None

        confidence = min(0.9, max(0.5, abs(deviation) / max(atr, 0.0001) * 0.2 + 0.5))
        return RawSignal(
            direction=direction,
            confidence=confidence,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            generated_at=datetime.now(timezone.utc),
            features={"atr": atr, "mean_price": mean_price, "deviation": deviation},
            metadata={"strategy_code": self.strategy_code},
        )
