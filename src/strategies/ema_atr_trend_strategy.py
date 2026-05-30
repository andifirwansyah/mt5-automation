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

    def generate_signal(
        self,
        market_snapshot: MarketSnapshot,
        regime: RegimeResult,
        config: dict[str, Any],
    ) -> RawSignal | None:
        if regime.regime not in (
            MarketRegimeType.TRENDING_BULLISH,
            MarketRegimeType.TRENDING_BEARISH,
        ):
            return None

        atr = float(
            regime.features.get(
                "atr",
                max(market_snapshot.high_price - market_snapshot.low_price, 0.01),
            )
        )

        pullback_max_distance_atr = float(config.get("pullback_max_distance_atr", 0.8))
        confirmation_min_body_atr = float(config.get("confirmation_min_body_atr", 0.25))
        pullback_touch_required = bool(config.get("pullback_touch_required", False))
        confirmation_bars = int(config.get("confirmation_bars", 2))

        allow_momentum_continuation = bool(
            config.get("allow_momentum_continuation", True)
        )
        momentum_min_body_atr = float(config.get("momentum_min_body_atr", 0.45))

        pullback_distance_atr = float(
            regime.features.get("pullback_distance_to_ema_fast_atr", 999.0)
        )
        pullback_touched_ema = bool(
            regime.features.get("pullback_touched_ema_fast", False)
        )
        body_atr_ratio = float(regime.features.get("body_atr_ratio", 0.0))
        confirmation_bullish = bool(regime.features.get("confirmation_bullish", False))
        confirmation_bearish = bool(regime.features.get("confirmation_bearish", False))

        # Jalur 1: pullback setup
        pullback_valid = pullback_distance_atr <= pullback_max_distance_atr

        if pullback_touch_required:
            pullback_valid = pullback_valid and pullback_touched_ema

        pullback_valid = pullback_valid and body_atr_ratio >= confirmation_min_body_atr

        # Jalur 2: momentum continuation setup
        momentum_valid = (
            allow_momentum_continuation
            and body_atr_ratio >= momentum_min_body_atr
        )

        sl_mult = float(config.get("sl_atr_multiplier", 1.5))
        tp_mult = float(config.get("tp_atr_multiplier", 2.5))

        entry = market_snapshot.close_price

        if regime.regime == MarketRegimeType.TRENDING_BULLISH:
            if confirmation_bars >= 2 and not confirmation_bullish:
                return None

            momentum_valid = momentum_valid and confirmation_bullish

            if not (pullback_valid or momentum_valid):
                return None

            direction = SignalDirection.BUY
            stop_loss = entry - (sl_mult * atr)
            take_profit = entry + (tp_mult * atr)

        else:
            if confirmation_bars >= 2 and not confirmation_bearish:
                return None

            momentum_valid = momentum_valid and confirmation_bearish

            if not (pullback_valid or momentum_valid):
                return None

            direction = SignalDirection.SELL
            stop_loss = entry + (sl_mult * atr)
            take_profit = entry - (tp_mult * atr)

        if pullback_valid and momentum_valid:
            setup_type = "pullback_and_momentum"
        elif momentum_valid:
            setup_type = "momentum_continuation"
        else:
            setup_type = "pullback"

        trend_strength = float(regime.features.get("trend_strength", 0.0))
        confidence = min(
            0.99,
            max(
                0.5,
                0.45 + (trend_strength * 0.15) + (body_atr_ratio * 0.2),
            ),
        )

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
                "pullback_valid": pullback_valid,
                "momentum_valid": momentum_valid,
                "allow_momentum_continuation": allow_momentum_continuation,
                "momentum_min_body_atr": momentum_min_body_atr,
                "setup_type": setup_type,
            },
            metadata={"strategy_code": self.strategy_code},
        )