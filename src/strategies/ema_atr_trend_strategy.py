"""EMA+ATR trend-following strategy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.domain.enums import MarketRegimeType, SignalDirection
from src.domain.models.market_snapshot import MarketSnapshot
from src.domain.models.regime_result import RegimeResult
from src.domain.models.signal import RawSignal
from src.strategies.base_strategy import BaseStrategy


class EmaAtrTrendStrategy(BaseStrategy):
    """Trend strategy for bullish/bearish trending regimes."""

    strategy_code = "EMA_ATR_TREND"

    def generate_signal(self, market_snapshot: MarketSnapshot, regime: RegimeResult, config: dict[str, Any]) -> RawSignal | None:
        if regime.regime not in (MarketRegimeType.TRENDING_BULLISH, MarketRegimeType.TRENDING_BEARISH):
            return None

        atr = float(regime.features.get("atr", max(market_snapshot.high_price - market_snapshot.low_price, 0.01)))
        sl_mult = float(config.get("sl_atr_multiplier", 1.5))
        tp_mult = float(config.get("tp_atr_multiplier", 2.5))

        entry = market_snapshot.close_price
        if regime.regime == MarketRegimeType.TRENDING_BULLISH:
            direction = SignalDirection.BUY
            stop_loss = entry - (sl_mult * atr)
            take_profit = entry + (tp_mult * atr)
        else:
            direction = SignalDirection.SELL
            stop_loss = entry + (sl_mult * atr)
            take_profit = entry - (tp_mult * atr)

        trend_strength = float(regime.features.get("trend_strength", 0.0))
        confidence = min(0.99, max(0.5, 0.5 + (trend_strength * 0.2)))

        return RawSignal(
            direction=direction,
            confidence=confidence,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            generated_at=datetime.now(timezone.utc),
            features={"atr": atr, "trend_strength": trend_strength},
            metadata={"strategy_code": self.strategy_code},
        )
