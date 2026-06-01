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
        confirmation_timeframes: list[str] | None = None,
        enable_multi_timeframe: bool = True,
        primary_timeframe_weight: float = 0.60,
        fusion_min_margin: float = 0.05,
    ) -> None:
        self.regime_repository = regime_repository
        self.ema_fast_period = ema_fast_period
        self.ema_slow_period = ema_slow_period
        self.atr_period = atr_period
        self.trend_threshold = trend_threshold
        self.choppy_threshold = choppy_threshold
        self.high_vol_threshold = high_vol_threshold
        self.low_vol_threshold = low_vol_threshold
        self.confirmation_timeframes = confirmation_timeframes or ["M15", "M30", "H1", "H4"]
        self.enable_multi_timeframe = enable_multi_timeframe
        self.primary_timeframe_weight = max(0.0, min(1.0, primary_timeframe_weight))
        self.fusion_min_margin = max(0.0, fusion_min_margin)

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

    @staticmethod
    def _regime_reason(regime: MarketRegimeType) -> str | None:
        if regime == MarketRegimeType.CHOPPY:
            return CHOPPY_MARKET_NO_TRADE
        if regime == MarketRegimeType.LOW_VOLATILITY:
            return LOW_VOLATILITY_NO_TRADE
        return None

    def _evaluate_regime_from_dataframe(self, df: pd.DataFrame) -> RegimeResult:
        close = pd.to_numeric(df["close"], errors="coerce")
        open_price = pd.to_numeric(df["open"], errors="coerce") if "open" in df.columns else close.shift(1).fillna(close)
        high = pd.to_numeric(df["high"], errors="coerce")
        low = pd.to_numeric(df["low"], errors="coerce")

        ema_fast = close.ewm(span=self.ema_fast_period, adjust=False).mean()
        ema_slow = close.ewm(span=self.ema_slow_period, adjust=False).mean()

        prev_close_series = close.shift(1)
        tr = pd.concat([(high - low).abs(), (high - prev_close_series).abs(), (low - prev_close_series).abs()], axis=1).max(axis=1)
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
        regime_reason = self._regime_reason(regime)
        is_tradeable = regime_reason is None

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
        return RegimeResult(
            regime=regime,
            confidence=confidence,
            is_tradeable=is_tradeable,
            reason=regime_reason,
            features=features,
        )

    def _fuse_regimes(
        self,
        *,
        primary_timeframe: str,
        primary_result: RegimeResult,
        confirmation_results: dict[str, RegimeResult],
    ) -> RegimeResult:
        merged_features = dict(primary_result.features)
        if not self.enable_multi_timeframe or not confirmation_results:
            merged_features["primary_timeframe"] = primary_timeframe
            merged_features["fused_regime"] = primary_result.regime.value
            merged_features["mtf_confirmation"] = {}
            merged_features["mtf_policy"] = self._build_mtf_policy(
                primary_timeframe=primary_timeframe,
                primary_result=primary_result,
                fused_regime=primary_result.regime,
                confirmation_results={},
            )
            return RegimeResult(
                regime=primary_result.regime,
                confidence=primary_result.confidence,
                is_tradeable=primary_result.is_tradeable,
                reason=primary_result.reason,
                features=merged_features,
            )

        vote_scores: dict[MarketRegimeType, float] = {regime: 0.0 for regime in MarketRegimeType}
        primary_weight = self.primary_timeframe_weight
        secondary_weight = (1.0 - primary_weight) / max(len(confirmation_results), 1)

        vote_scores[primary_result.regime] += primary_weight * float(primary_result.confidence)
        confirmation_payload: dict[str, Any] = {}
        for timeframe, result in confirmation_results.items():
            vote_scores[result.regime] += secondary_weight * float(result.confidence)
            confirmation_payload[timeframe] = {
                "regime": result.regime.value,
                "confidence": result.confidence,
                "is_tradeable": result.is_tradeable,
                "reason": result.reason,
            }

        ranked_votes = sorted(vote_scores.items(), key=lambda item: item[1], reverse=True)
        winner_regime, winner_score = ranked_votes[0]
        second_score = ranked_votes[1][1] if len(ranked_votes) > 1 else 0.0

        if (winner_score - second_score) < self.fusion_min_margin:
            winner_regime = primary_result.regime

        if primary_result.reason is not None:
            fused_regime = primary_result.regime
            fused_reason = primary_result.reason
            fused_tradeable = False
        else:
            fused_regime = winner_regime
            fused_reason = self._regime_reason(fused_regime)
            fused_tradeable = fused_reason is None

        same_as_winner = 1
        same_as_winner += sum(1 for result in confirmation_results.values() if result.regime == fused_regime)
        total_frames = 1 + len(confirmation_results)
        consensus_ratio = same_as_winner / max(total_frames, 1)

        merged_features.update(
            {
                "primary_timeframe": primary_timeframe,
                "primary_regime": primary_result.regime.value,
                "primary_confidence": primary_result.confidence,
                "fused_regime": fused_regime.value,
                "mtf_confirmation": confirmation_payload,
                "mtf_vote_scores": {regime.value: score for regime, score in vote_scores.items() if score > 0.0},
                "mtf_consensus_ratio": consensus_ratio,
                "mtf_alignment_with_primary": fused_regime == primary_result.regime,
            }
        )

        merged_features["mtf_policy"] = self._build_mtf_policy(
            primary_timeframe=primary_timeframe,
            primary_result=primary_result,
            fused_regime=fused_regime,
            confirmation_results=confirmation_results,
        )

        fused_confidence = min(0.99, max(primary_result.confidence, winner_score))
        return RegimeResult(
            regime=fused_regime,
            confidence=fused_confidence,
            is_tradeable=fused_tradeable,
            reason=fused_reason,
            features=merged_features,
        )

    @staticmethod
    def _regime_to_direction_bias(regime: MarketRegimeType) -> str:
        if regime == MarketRegimeType.TRENDING_BULLISH:
            return "BUY"
        if regime == MarketRegimeType.TRENDING_BEARISH:
            return "SELL"
        return "BOTH"

    @staticmethod
    def _extract_layer_regime(layer_timeframes: list[str], confirmation_results: dict[str, RegimeResult]) -> MarketRegimeType | None:
        for timeframe in layer_timeframes:
            result = confirmation_results.get(timeframe)
            if result is not None:
                return result.regime
        return None

    def _build_mtf_policy(
        self,
        *,
        primary_timeframe: str,
        primary_result: RegimeResult,
        fused_regime: MarketRegimeType,
        confirmation_results: dict[str, RegimeResult],
    ) -> dict[str, Any]:
        macro_regime = self._extract_layer_regime(["H4", "H1"], confirmation_results)
        meso_regime = self._extract_layer_regime(["M30", "M15"], confirmation_results)
        trigger_regime = primary_result.regime

        macro_bias = self._regime_to_direction_bias(macro_regime) if macro_regime is not None else self._regime_to_direction_bias(fused_regime)
        allowed_directions = ["BUY", "SELL"]
        preferred_tokens: list[str] = []

        if macro_bias == "BUY":
            allowed_directions = ["BUY"]
            preferred_tokens = ["EMA_ATR_TREND", "TREND", "VOLATILITY_BREAKOUT"]
        elif macro_bias == "SELL":
            allowed_directions = ["SELL"]
            preferred_tokens = ["EMA_ATR_TREND", "TREND", "VOLATILITY_BREAKOUT"]
        elif fused_regime == MarketRegimeType.RANGING:
            preferred_tokens = ["RANGE_REVERSION", "REVERSION"]
        elif fused_regime == MarketRegimeType.HIGH_VOLATILITY:
            preferred_tokens = ["VOLATILITY_BREAKOUT", "LIQUIDITY_SWEEP_REVERSAL", "BREAKOUT", "SWEEP"]

        block_trade = False
        block_reason = None
        setup_ready = True
        setup_reason = "LAYER_POLICY_OK"

        if trigger_regime in (MarketRegimeType.CHOPPY, MarketRegimeType.LOW_VOLATILITY):
            block_trade = True
            block_reason = trigger_regime.value
            setup_ready = False
            setup_reason = "TRIGGER_NOT_TRADEABLE"
        elif meso_regime in (MarketRegimeType.CHOPPY, MarketRegimeType.LOW_VOLATILITY):
            setup_ready = False
            setup_reason = "MESO_LAYER_NOT_READY"

        return {
            "enabled": True,
            "primary_timeframe": primary_timeframe,
            "macro_layer": {
                "timeframes": ["H4", "H1"],
                "regime": macro_regime.value if macro_regime is not None else None,
                "bias": macro_bias,
            },
            "meso_layer": {
                "timeframes": ["M30", "M15"],
                "regime": meso_regime.value if meso_regime is not None else None,
                "setup_ready": setup_ready,
                "setup_reason": setup_reason,
            },
            "trigger_layer": {
                "timeframe": primary_timeframe,
                "regime": trigger_regime.value,
            },
            "fused_regime": fused_regime.value,
            "allowed_directions": allowed_directions,
            "preferred_strategy_tokens": preferred_tokens,
            "block_trade": block_trade,
            "block_reason": block_reason,
        }

    def run(self, context: TradingContext) -> TradingContext:
        ingestion = context.ingestion_result or {}
        rates_map = ingestion.get("rates_by_timeframe", {})
        raw = rates_map.get(context.timeframe)
        df = self._to_dataframe(raw)

        if df.empty or len(df) < max(self.ema_slow_period, self.atr_period) + 2:
            context.reject("REGIME_DATA_INSUFFICIENT", {"message": "Not enough candles for regime calculation"})
            return context

        primary_result = self._evaluate_regime_from_dataframe(df)

        confirmation_results: dict[str, RegimeResult] = {}
        if self.enable_multi_timeframe:
            min_rows = max(self.ema_slow_period, self.atr_period) + 2
            for timeframe in self.confirmation_timeframes:
                if timeframe == context.timeframe:
                    continue
                raw_tf = rates_map.get(timeframe)
                if raw_tf is None:
                    continue
                tf_df = self._to_dataframe(raw_tf)
                if tf_df.empty or len(tf_df) < min_rows:
                    continue
                confirmation_results[timeframe] = self._evaluate_regime_from_dataframe(tf_df)

        context.regime_result = self._fuse_regimes(
            primary_timeframe=context.timeframe,
            primary_result=primary_result,
            confirmation_results=confirmation_results,
        )

        symbol_id = ingestion.get("symbol_id")
        timeframe_ids = ingestion.get("timeframe_ids") or {}
        timeframe_id = timeframe_ids.get(context.timeframe)
        if symbol_id and timeframe_id:
            self.regime_repository.create_market_regime(
                symbol_id=symbol_id,
                timeframe_id=timeframe_id,
                regime=context.regime_result.regime.value,
                confidence=context.regime_result.confidence,
                detected_at=context.candle_time,
                features=context.regime_result.features,
            )
            for timeframe, result in confirmation_results.items():
                tf_id = timeframe_ids.get(timeframe)
                if not tf_id:
                    continue
                self.regime_repository.create_market_regime(
                    symbol_id=symbol_id,
                    timeframe_id=tf_id,
                    regime=result.regime.value,
                    confidence=result.confidence,
                    detected_at=context.candle_time,
                    features={
                        **result.features,
                        "source": "mtf_confirmation",
                        "primary_timeframe": context.timeframe,
                        "fused_regime": context.regime_result.regime.value,
                    },
                )
            self.regime_repository.session.commit()

        return context
