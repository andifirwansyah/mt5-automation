"""Market regime engine based on EMA, ATR, trend strength, and volatility score."""

from __future__ import annotations

import math
from typing import Any

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None  # type: ignore[assignment]

from src.domain.enums import MarketRegimeType
from src.domain.models.regime_result import RegimeResult
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.rejection_reason import CHOPPY_MARKET_NO_TRADE, LOW_VOLATILITY_NO_TRADE
from src.pipeline.trading_context import TradingContext
from src.repositories.regime_repository import RegimeRepository


class MarketRegimeEngine(PipelineStep):
    """Compute market regime from historical OHLCV context."""

    @property
    def name(self) -> str:
        return "MarketRegimeEngine"

    def __init__(
        self,
        regime_repository: RegimeRepository,
        ema_fast_period: int = 20,
        ema_slow_period: int = 50,
        atr_period: int = 14,
        trend_threshold: float = 0.8,
        choppy_threshold: float = 0.3,
        high_vol_threshold: float = 0.003,
        low_vol_threshold: float = 0.001,
    ) -> None:
        self.regime_repository = regime_repository
        self.ema_fast_period = ema_fast_period
        self.ema_slow_period = ema_slow_period
        self.atr_period = atr_period
        self.trend_threshold = trend_threshold
        self.choppy_threshold = choppy_threshold
        self.high_vol_threshold = high_vol_threshold
        self.low_vol_threshold = low_vol_threshold

    @staticmethod
    def _to_dataframe(frame_like: Any) -> pd.DataFrame:
        if pd is None:
            raise RuntimeError("pandas is required for MarketRegimeEngine")
        if isinstance(frame_like, pd.DataFrame):
            return frame_like.copy()
        if frame_like is None:
            return pd.DataFrame()
        if hasattr(frame_like, "iterrows"):
            rows: list[dict[str, Any]] = []
            for _, row in frame_like.iterrows():
                rows.append(row.to_dict() if hasattr(row, "to_dict") else dict(row))
            return pd.DataFrame(rows)
        return pd.DataFrame(frame_like)

    def run(self, context: TradingContext) -> TradingContext:
        ingestion = context.ingestion_result or {}
        rates_map = ingestion.get("rates_by_timeframe", {})
        raw = rates_map.get(context.timeframe)
        df = self._to_dataframe(raw)

        if df.empty or len(df) < max(self.ema_slow_period, self.atr_period) + 2:
            context.reject("REGIME_DATA_INSUFFICIENT", {"message": "Not enough candles for regime calculation"})
            return context

        close = pd.to_numeric(df["close"], errors="coerce")
        open_price = pd.to_numeric(df["open"], errors="coerce") if "open" in df.columns else close.shift(1).fillna(close)
        high = pd.to_numeric(df["high"], errors="coerce")
        low = pd.to_numeric(df["low"], errors="coerce")

        ema_fast = close.ewm(span=self.ema_fast_period, adjust=False).mean()
        ema_slow = close.ewm(span=self.ema_slow_period, adjust=False).mean()

        prev_close = close.shift(1)
        tr = pd.concat([(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        atr = tr.rolling(self.atr_period).mean()

        ema_fast_val = float(ema_fast.iloc[-1])
        ema_slow_val = float(ema_slow.iloc[-1])
        atr_val = float(atr.iloc[-1]) if not math.isnan(float(atr.iloc[-1])) else float((high - low).tail(self.atr_period).mean())
        close_val = float(close.iloc[-1])

        trend_strength = abs(ema_fast_val - ema_slow_val) / max(atr_val, 1e-8)
        volatility_score = atr_val / max(close_val, 1e-8)

        breakout_lookback = 20
        range_lookback = 30

        prev_range_high = None
        prev_range_low = None
        prev_range_width = None
        if len(df) >= breakout_lookback + 1:
            prev_window = df.iloc[-(breakout_lookback + 1) : -1]
            prev_range_high = float(pd.to_numeric(prev_window["high"], errors="coerce").max())
            prev_range_low = float(pd.to_numeric(prev_window["low"], errors="coerce").min())
            prev_range_width = prev_range_high - prev_range_low

        range_high = None
        range_low = None
        range_mid = None
        range_width = None
        if len(df) >= range_lookback:
            range_window = df.iloc[-range_lookback:]
            range_high = float(pd.to_numeric(range_window["high"], errors="coerce").max())
            range_low = float(pd.to_numeric(range_window["low"], errors="coerce").min())
            range_mid = (range_high + range_low) / 2.0
            range_width = range_high - range_low

        last_open = float(open_price.iloc[-1])
        last_close = close_val
        last_high = float(high.iloc[-1])
        last_low = float(low.iloc[-1])
        last_body = abs(last_close - last_open)
        body_atr_ratio = last_body / max(atr_val, 1e-8)

        prev_open = float(open_price.iloc[-2]) if len(open_price) >= 2 else last_open
        prev_close = float(close.iloc[-2]) if len(close) >= 2 else last_close
        prev_body = abs(prev_close - prev_open)

        last_direction = 1 if last_close > last_open else (-1 if last_close < last_open else 0)
        prev_direction = 1 if prev_close > prev_open else (-1 if prev_close < prev_open else 0)

        confirmation_bullish = bool(last_direction > 0 and prev_direction >= 0 and last_close > ema_fast_val)
        confirmation_bearish = bool(last_direction < 0 and prev_direction <= 0 and last_close < ema_fast_val)

        pullback_distance_to_ema_fast_atr = abs(last_close - ema_fast_val) / max(atr_val, 1e-8)
        pullback_touched_ema_fast = bool(last_low <= ema_fast_val <= last_high)

        if volatility_score >= self.high_vol_threshold:
            regime = MarketRegimeType.HIGH_VOLATILITY
        elif trend_strength <= self.choppy_threshold:
            regime = MarketRegimeType.CHOPPY
        elif ema_fast_val > ema_slow_val and trend_strength >= self.trend_threshold:
            regime = MarketRegimeType.TRENDING_BULLISH
        elif ema_fast_val < ema_slow_val and trend_strength >= self.trend_threshold:
            regime = MarketRegimeType.TRENDING_BEARISH
        elif volatility_score <= self.low_vol_threshold:
            regime = MarketRegimeType.LOW_VOLATILITY
        else:
            regime = MarketRegimeType.RANGING

        confidence = min(0.99, max(0.3, (trend_strength * 0.2) + (volatility_score * 10)))
        if regime == MarketRegimeType.CHOPPY:
            is_tradeable = False
            regime_reason = CHOPPY_MARKET_NO_TRADE
        elif regime == MarketRegimeType.LOW_VOLATILITY:
            is_tradeable = False
            regime_reason = LOW_VOLATILITY_NO_TRADE
        else:
            is_tradeable = True
            regime_reason = None

        features = {
            "ema_fast": ema_fast_val,
            "ema_slow": ema_slow_val,
            "atr": atr_val,
            "trend_strength": trend_strength,
            "volatility_score": volatility_score,
            "last_open": last_open,
            "last_close": last_close,
            "last_high": last_high,
            "last_low": last_low,
            "last_body": last_body,
            "prev_open": prev_open,
            "prev_close": prev_close,
            "prev_body": prev_body,
            "body_atr_ratio": body_atr_ratio,
            "last_direction": last_direction,
            "prev_direction": prev_direction,
            "confirmation_bullish": confirmation_bullish,
            "confirmation_bearish": confirmation_bearish,
            "pullback_distance_to_ema_fast_atr": pullback_distance_to_ema_fast_atr,
            "pullback_touched_ema_fast": pullback_touched_ema_fast,
            "prev_range_high": prev_range_high,
            "prev_range_low": prev_range_low,
            "prev_range_width": prev_range_width,
            "prev_range_lookback_bars": breakout_lookback,
            "range_high": range_high,
            "range_low": range_low,
            "range_mid": range_mid,
            "range_width": range_width,
            "range_lookback_bars": range_lookback,
        }

        context.regime_result = RegimeResult(
            regime=regime,
            confidence=confidence,
            is_tradeable=is_tradeable,
            reason=regime_reason,
            features=features,
        )

        symbol_id = ingestion.get("symbol_id")
        timeframe_id = (ingestion.get("timeframe_ids") or {}).get(context.timeframe)
        if symbol_id and timeframe_id:
            self.regime_repository.create_market_regime(
                symbol_id=symbol_id,
                timeframe_id=timeframe_id,
                regime=regime.value,
                confidence=confidence,
                detected_at=context.candle_time,
                features=features,
            )
            self.regime_repository.session.commit()

        return context
