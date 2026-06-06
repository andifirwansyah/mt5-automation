"""Market Structure Engine for support/resistance location context."""

from __future__ import annotations

from typing import Any

from loguru import logger

from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.trading.market_structure.config import MarketStructureConfig
from src.trading.market_structure.models import MarketStructureResult, PriceZone, StructurePoint, StructureTrend
from src.trading.technical_analysis.patterns.swing_detector import detect_swing_points


class MarketStructureEngine(PipelineStep):
    """Detect nearest support/resistance and valid entry location zones."""

    @property
    def name(self) -> str:
        return "MarketStructureEngine"

    def __init__(self, config: MarketStructureConfig | None = None, settings: Any | None = None) -> None:
        self.config = config or MarketStructureConfig()
        self.settings = settings

    def _effective_config(self) -> MarketStructureConfig:
        if self.settings is None:
            return self.config

        runtime_config = MarketStructureConfig.from_settings(self.settings)
        runtime_config.enabled = self.config.enabled
        runtime_config.max_candles_lookback = self.config.max_candles_lookback
        runtime_config.swing_left_bars = self.config.swing_left_bars
        runtime_config.swing_right_bars = self.config.swing_right_bars
        runtime_config.swing_min_distance_atr = self.config.swing_min_distance_atr
        runtime_config.fallback_atr = self.config.fallback_atr
        return runtime_config

    @staticmethod
    def _to_candle_rows(frame_like: Any) -> list[dict[str, Any]]:
        if frame_like is None:
            return []
        if hasattr(frame_like, "to_dict") and hasattr(frame_like, "columns"):
            try:
                return list(frame_like.to_dict(orient="records"))
            except TypeError:
                pass
        if isinstance(frame_like, list):
            rows: list[dict[str, Any]] = []
            for row in frame_like:
                rows.append(row if isinstance(row, dict) else dict(row))
            return rows
        return []

    def _extract_candles(self, context: TradingContext) -> list[dict[str, Any]]:
        ingestion = context.ingestion_result or {}
        rates_by_timeframe = ingestion.get("rates_by_timeframe") or {}
        rows = self._to_candle_rows(rates_by_timeframe.get(context.timeframe))
        if len(rows) > self.config.max_candles_lookback:
            return rows[-self.config.max_candles_lookback :]
        return rows

    def _estimate_atr(self, candles: list[dict[str, Any]]) -> float:
        ranges: list[float] = []
        for row in candles[-14:]:
            high = float(row.get("high", 0.0) or 0.0)
            low = float(row.get("low", 0.0) or 0.0)
            if high > 0 or low > 0:
                ranges.append(abs(high - low))
        if not ranges:
            return max(1e-8, float(self.config.fallback_atr))
        return max(1e-8, sum(ranges) / len(ranges))

    @staticmethod
    def _last_close(context: TradingContext, candles: list[dict[str, Any]]) -> float:
        if candles:
            return float(candles[-1].get("close", 0.0) or 0.0)
        if context.market_snapshot is not None:
            return float(context.market_snapshot.close_price)
        return 0.0

    @staticmethod
    def _infer_trend_structure(supports: list[StructurePoint], resistances: list[StructurePoint], context: TradingContext) -> StructureTrend:
        last_lows = supports[-2:]
        last_highs = resistances[-2:]
        if len(last_lows) < 2 or len(last_highs) < 2:
            if context.regime_result is not None:
                regime_value = context.regime_result.regime.value
                if regime_value == "TRENDING_BULLISH":
                    return "BULLISH"
                if regime_value == "TRENDING_BEARISH":
                    return "BEARISH"
            return "UNCLEAR"

        higher_low = last_lows[-1].price > last_lows[-2].price
        higher_high = last_highs[-1].price > last_highs[-2].price
        lower_low = last_lows[-1].price < last_lows[-2].price
        lower_high = last_highs[-1].price < last_highs[-2].price

        if higher_low and higher_high:
            return "BULLISH"
        if lower_low and lower_high:
            return "BEARISH"
        return "RANGING"

    @staticmethod
    def _nearest_below(price: float, levels: list[StructurePoint]) -> StructurePoint | None:
        below = [level for level in levels if level.price <= price]
        if not below:
            return None
        return min(below, key=lambda level: abs(price - level.price))

    @staticmethod
    def _nearest_above(price: float, levels: list[StructurePoint]) -> StructurePoint | None:
        above = [level for level in levels if level.price >= price]
        if not above:
            return None
        return min(above, key=lambda level: abs(level.price - price))

    @staticmethod
    def _nearest_broken_resistance(price: float, levels: list[StructurePoint]) -> StructurePoint | None:
        below = [level for level in levels if level.price < price]
        if not below:
            return None
        return min(below, key=lambda level: abs(price - level.price))

    @staticmethod
    def _nearest_broken_support(price: float, levels: list[StructurePoint]) -> StructurePoint | None:
        above = [level for level in levels if level.price > price]
        if not above:
            return None
        return min(above, key=lambda level: abs(level.price - price))

    def _build_zone(self, point: StructurePoint, atr: float) -> PriceZone:
        tolerance = max(0.0, atr * self.config.zone_tolerance_atr)
        return PriceZone(kind=point.kind, center=point.price, low=point.price - tolerance, high=point.price + tolerance)

    def _fallback_result(self, context: TradingContext, reason: str) -> MarketStructureResult:
        price = context.market_snapshot.close_price if context.market_snapshot is not None else 0.0
        return MarketStructureResult(
            symbol=context.symbol,
            timeframe=context.timeframe,
            trend_structure="UNCLEAR",
            current_price=float(price),
            atr=max(1e-8, float(self.config.fallback_atr)),
            notes=[reason],
            metadata={"mode": "safe_unclear", "reason": reason, "trace_id": str(context.trace_id)},
        )

    def run(self, context: TradingContext) -> TradingContext:
        log = logger.bind(trace_id=str(context.trace_id), engine=self.name)
        log.info("MARKET_STRUCTURE_STARTED")

        self.config = self._effective_config()

        if not self.config.enabled:
            context.market_structure = self._fallback_result(context, "MARKET_STRUCTURE_DISABLED")
            return context

        try:
            candles = self._extract_candles(context)
            if len(candles) < self.config.min_candles_required:
                context.market_structure = self._fallback_result(context, "MARKET_STRUCTURE_DATA_INSUFFICIENT")
                context.market_structure.metadata["candles_count"] = len(candles)
                return context

            regime_atr = None
            if context.regime_result is not None:
                regime_atr = (context.regime_result.features or {}).get("atr")
            atr = float(regime_atr) if regime_atr not in (None, 0, 0.0) else self._estimate_atr(candles)
            current_price = self._last_close(context, candles)

            swing_highs, swing_lows = detect_swing_points(
                candles=candles,
                left_bars=self.config.swing_left_bars,
                right_bars=self.config.swing_right_bars,
                atr=atr,
                min_distance_atr=self.config.swing_min_distance_atr,
            )
            supports = [StructurePoint(price=p.price, kind="support", index=p.index, candle_time=p.candle_time) for p in swing_lows]
            resistances = [StructurePoint(price=p.price, kind="resistance", index=p.index, candle_time=p.candle_time) for p in swing_highs]

            nearest_support = self._nearest_below(current_price, supports)
            nearest_resistance = self._nearest_above(current_price, resistances)
            support_zone = self._build_zone(nearest_support, atr) if nearest_support else None
            resistance_zone = self._build_zone(nearest_resistance, atr) if nearest_resistance else None

            distance_to_support = abs(current_price - nearest_support.price) if nearest_support else None
            distance_to_resistance = abs(nearest_resistance.price - current_price) if nearest_resistance else None
            danger_distance = max(0.0, atr * self.config.danger_zone_atr)
            minimum_room = max(0.0, atr * self.config.minimum_room_to_zone_atr)

            is_near_support = bool(support_zone and support_zone.contains(current_price))
            is_near_resistance = bool(resistance_zone and resistance_zone.contains(current_price))
            room_to_resistance_ok = distance_to_resistance is None or distance_to_resistance >= minimum_room
            room_to_support_ok = distance_to_support is None or distance_to_support >= minimum_room
            too_close_to_resistance = distance_to_resistance is not None and distance_to_resistance <= danger_distance
            too_close_to_support = distance_to_support is not None and distance_to_support <= danger_distance

            trend_structure = self._infer_trend_structure(supports, resistances, context)
            broken_resistance = self._nearest_broken_resistance(current_price, resistances)
            broken_support = self._nearest_broken_support(current_price, supports)
            break_of_structure = bool(broken_resistance and (current_price - broken_resistance.price) <= atr) or bool(
                broken_support and (broken_support.price - current_price) <= atr
            )
            liquidity_sweep = bool(((context.regime_result.features if context.regime_result else {}) or {}).get("liquidity_sweep_detected", False))

            valid_buy_zone = (is_near_support or trend_structure == "BULLISH" or break_of_structure) and room_to_resistance_ok and not too_close_to_resistance
            valid_sell_zone = (is_near_resistance or trend_structure == "BEARISH" or break_of_structure) and room_to_support_ok and not too_close_to_support

            notes: list[str] = []
            if nearest_support is None:
                notes.append("NO_SUPPORT_BELOW_PRICE")
            if nearest_resistance is None:
                notes.append("NO_RESISTANCE_ABOVE_PRICE")
            if not valid_buy_zone and not valid_sell_zone:
                notes.append("PRICE_IN_NO_TRADE_ZONE")

            context.market_structure = MarketStructureResult(
                symbol=context.symbol,
                timeframe=context.timeframe,
                trend_structure=trend_structure,
                current_price=current_price,
                atr=atr,
                nearest_support=nearest_support.price if nearest_support else None,
                nearest_resistance=nearest_resistance.price if nearest_resistance else None,
                distance_to_support_points=distance_to_support,
                distance_to_resistance_points=distance_to_resistance,
                is_near_support=is_near_support,
                is_near_resistance=is_near_resistance,
                valid_buy_zone=valid_buy_zone,
                valid_sell_zone=valid_sell_zone,
                break_of_structure=break_of_structure,
                liquidity_sweep_detected=liquidity_sweep,
                support_zones=[support_zone] if support_zone else [],
                resistance_zones=[resistance_zone] if resistance_zone else [],
                swing_points=[*supports[-5:], *resistances[-5:]],
                notes=notes,
                metadata={
                    "trace_id": str(context.trace_id),
                    "candles_count": len(candles),
                    "support_count": len(supports),
                    "resistance_count": len(resistances),
                    "zone_tolerance_atr": self.config.zone_tolerance_atr,
                    "danger_zone_atr": self.config.danger_zone_atr,
                    "minimum_room_to_zone_atr": self.config.minimum_room_to_zone_atr,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive runtime safety
            log.warning("MARKET_STRUCTURE_FAILED_SAFE_FALLBACK error={}", str(exc))
            context.market_structure = self._fallback_result(context, "MARKET_STRUCTURE_ERROR")
            context.market_structure.metadata["error_message"] = str(exc)

        log.info(
            "MARKET_STRUCTURE_COMPLETED trend={} buy_zone={} sell_zone={} support={} resistance={}",
            context.market_structure.trend_structure,
            context.market_structure.valid_buy_zone,
            context.market_structure.valid_sell_zone,
            context.market_structure.nearest_support,
            context.market_structure.nearest_resistance,
        )
        return context
