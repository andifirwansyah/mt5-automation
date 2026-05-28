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
        pullback_max_distance_atr = float(config.get("pullback_max_distance_atr", 0.8))
        confirmation_min_body_atr = float(config.get("confirmation_min_body_atr", 0.3))
        pullback_touch_required = bool(config.get("pullback_touch_required", True))
        confirmation_bars = int(config.get("confirmation_bars", 2))

        pullback_distance_atr = float(regime.features.get("pullback_distance_to_ema_fast_atr", 999.0))
        pullback_touched_ema = bool(regime.features.get("pullback_touched_ema_fast", False))
        body_atr_ratio = float(regime.features.get("body_atr_ratio", 0.0))
        confirmation_bullish = bool(regime.features.get("confirmation_bullish", False))
        confirmation_bearish = bool(regime.features.get("confirmation_bearish", False))

        if pullback_distance_atr > pullback_max_distance_atr:
            return None
        if pullback_touch_required and not pullback_touched_ema:
            return None
        if body_atr_ratio < confirmation_min_body_atr:
            return None

        sl_mult = float(config.get("sl_atr_multiplier", 1.5))
        tp_mult = float(config.get("tp_atr_multiplier", 2.5))

        entry = market_snapshot.close_price
        if regime.regime == MarketRegimeType.TRENDING_BULLISH:
            if confirmation_bars >= 2 and not confirmation_bullish:
                return None
            direction = SignalDirection.BUY
            stop_loss = entry - (sl_mult * atr)
            take_profit = entry + (tp_mult * atr)
        else:
            if confirmation_bars >= 2 and not confirmation_bearish:
                return None
            direction = SignalDirection.SELL
            stop_loss = entry + (sl_mult * atr)
            take_profit = entry - (tp_mult * atr)

        trend_strength = float(regime.features.get("trend_strength", 0.0))
        confidence = min(0.99, max(0.5, 0.45 + (trend_strength * 0.15) + (body_atr_ratio * 0.2)))

        return RawSignal(
            direction=direction,
            confidence=confidence,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            generated_at=datetime.now(timezone.utc),
            features={
                "atr": atr,
                "trend_strength": trend_strength,
                "pullback_distance_atr": pullback_distance_atr,
                "pullback_touched_ema_fast": pullback_touched_ema,
                "body_atr_ratio": body_atr_ratio,
            },
            metadata={"strategy_code": self.strategy_code},
        )
