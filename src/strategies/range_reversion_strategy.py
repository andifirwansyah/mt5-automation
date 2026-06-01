"""Range mean-reversion strategy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.domain.enums import MarketRegimeType, SignalDirection
from src.domain.models.market_snapshot import MarketSnapshot
from src.domain.models.regime_result import RegimeResult
from src.domain.models.signal import RawSignal
from src.strategies.base_strategy import BaseStrategy
from src.strategies.pattern_evidence_utils import has_pattern_status, is_pattern_enabled
from src.trading.technical_analysis.models import TechnicalAnalysisResult


class RangeReversionStrategy(BaseStrategy):
    """Mean reversion strategy for ranging markets."""

    strategy_code = "RANGE_REVERSION"

    def generate_signal(
        self,
        market_snapshot: MarketSnapshot,
        regime: RegimeResult,
        config: dict[str, Any],
        technical_analysis: TechnicalAnalysisResult | None = None,
    ) -> RawSignal | None:
        if regime.regime != MarketRegimeType.RANGING:
            return None

        atr = float(regime.features.get("atr", max(market_snapshot.high_price - market_snapshot.low_price, 0.01)))
        range_high = regime.features.get("range_high")
        range_low = regime.features.get("range_low")
        range_mid = regime.features.get("range_mid")
        range_width = regime.features.get("range_width")
        if range_high is None or range_low is None or range_mid is None or range_width is None:
            return None

        range_high = float(range_high)
        range_low = float(range_low)
        range_mid = float(range_mid)
        range_width = float(range_width)
        if range_high <= range_low:
            return None

        min_range_width_atr = float(config.get("min_range_width_atr", 1.0))
        if range_width < (min_range_width_atr * atr):
            return None

        mean_price = float(regime.features.get("ema_slow", range_mid))
        reversion_threshold = float(config.get("reversion_threshold_atr", 0.4)) * atr
        boundary_tolerance = float(config.get("boundary_tolerance_atr", 0.25)) * atr
        min_body_atr = float(config.get("reversion_min_body_atr", 0.10))
        body_atr_ratio = float(regime.features.get("body_atr_ratio", 0.0))
        if body_atr_ratio < min_body_atr:
            return None

        entry = market_snapshot.close_price
        deviation = entry - mean_price
        near_upper_boundary = entry >= (range_high - boundary_tolerance)
        near_lower_boundary = entry <= (range_low + boundary_tolerance)

        sl_mult = float(config.get("sl_atr_multiplier", 1.2))
        tp_mult = float(config.get("tp_atr_multiplier", 1.8))

        if near_upper_boundary and deviation >= reversion_threshold:
            direction = SignalDirection.SELL
            stop_loss = entry + (sl_mult * atr)
            take_profit = entry - (tp_mult * atr)
        elif near_lower_boundary and deviation <= -reversion_threshold:
            direction = SignalDirection.BUY
            stop_loss = entry - (sl_mult * atr)
            take_profit = entry + (tp_mult * atr)
        else:
            return None

        confidence = min(0.9, max(0.5, abs(deviation) / max(atr, 0.0001) * 0.15 + (body_atr_ratio * 0.2) + 0.45))
        pattern_notes: list[str] = []

        if is_pattern_enabled(config):
            pe = config.get("pattern_evidence") or {}
            support_count = 0
            if direction == SignalDirection.SELL and bool(pe.get("double_top_enabled", True)):
                allowed = {"detected", "waiting_neckline_break", "weak_neckline_break", "neckline_broken"}
                if bool(pe.get("require_neckline_break", False)):
                    allowed = {"neckline_broken"}
                if has_pattern_status(technical_analysis, "DOUBLE_TOP", allowed):
                    support_count += 1
                    confidence += float(pe.get("double_top_bonus", 0.16))
                    pattern_notes.append("double_top_support")
                if has_pattern_status(technical_analysis, "DOUBLE_TOP", {"neckline_broken"}):
                    confidence += float(pe.get("neckline_break_bonus", 0.12))

            if direction == SignalDirection.BUY and bool(pe.get("double_bottom_enabled", True)):
                allowed = {"detected", "waiting_neckline_break", "weak_neckline_break", "neckline_broken"}
                if bool(pe.get("require_neckline_break", False)):
                    allowed = {"neckline_broken"}
                if has_pattern_status(technical_analysis, "DOUBLE_BOTTOM", allowed):
                    support_count += 1
                    confidence += float(pe.get("double_bottom_bonus", 0.16))
                    pattern_notes.append("double_bottom_support")
                if has_pattern_status(technical_analysis, "DOUBLE_BOTTOM", {"neckline_broken"}):
                    confidence += float(pe.get("neckline_break_bonus", 0.12))

            if bool(pe.get("use_as_hard_requirement", False)) and support_count == 0:
                return None

        confidence = min(0.99, max(0.45, confidence))
        return RawSignal(
            direction=direction,
            confidence=confidence,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            generated_at=datetime.now(timezone.utc),
            features={
                "atr": atr,
                "mean_price": mean_price,
                "deviation": deviation,
                "range_high": range_high,
                "range_low": range_low,
                "range_mid": range_mid,
                "range_width": range_width,
                "near_upper_boundary": near_upper_boundary,
                "near_lower_boundary": near_lower_boundary,
                "body_atr_ratio": body_atr_ratio,
                "pattern_evidence_notes": pattern_notes,
            },
            metadata={"strategy_code": self.strategy_code},
        )
