"""Volatility breakout strategy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.domain.enums import MarketRegimeType, SignalDirection
from src.domain.models.market_snapshot import MarketSnapshot
from src.domain.models.regime_result import RegimeResult
from src.domain.models.signal import RawSignal
from src.strategies.base_strategy import BaseStrategy
from src.strategies.pattern_evidence_utils import count_fvg, has_pattern_status, is_pattern_enabled
from src.trading.technical_analysis.models import TechnicalAnalysisResult


class VolatilityBreakoutStrategy(BaseStrategy):
    """Breakout strategy for high volatility condition."""

    strategy_code = "VOLATILITY_BREAKOUT"

    def generate_signal(
        self,
        market_snapshot: MarketSnapshot,
        regime: RegimeResult,
        config: dict[str, Any],
        technical_analysis: TechnicalAnalysisResult | None = None,
    ) -> RawSignal | None:
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

        min_breakout_range_atr = float(config.get("min_breakout_range_atr", 0.7))
        if (prev_range_high - prev_range_low) < (min_breakout_range_atr * atr):
            return None

        breakout_buffer = float(config.get("breakout_buffer_atr", 0.08)) * atr
        min_body_atr = float(config.get("breakout_min_body_atr", 0.15))
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
        pattern_notes: list[str] = []

        if is_pattern_enabled(config):
            pe = config.get("pattern_evidence") or {}
            support_count = 0
            if direction == SignalDirection.SELL and bool(pe.get("allow_double_top_neckline_break", True)):
                if has_pattern_status(technical_analysis, "DOUBLE_TOP", {"neckline_broken"}):
                    support_count += 1
                    confidence += float(pe.get("neckline_break_bonus", 0.12))
                    pattern_notes.append("double_top_neckline_break")

            if direction == SignalDirection.BUY and bool(pe.get("allow_double_bottom_neckline_break", True)):
                if has_pattern_status(technical_analysis, "DOUBLE_BOTTOM", {"neckline_broken"}):
                    support_count += 1
                    confidence += float(pe.get("neckline_break_bonus", 0.12))
                    pattern_notes.append("double_bottom_neckline_break")

            if bool(pe.get("fvg_confirmation_enabled", True)):
                fvg_type = "bullish_fvg" if direction == SignalDirection.BUY else "bearish_fvg"
                fvg_count = count_fvg(technical_analysis, fvg_type, {"open", "partial"})
                if fvg_count > 0:
                    support_count += 1
                    confidence += float(pe.get("fvg_after_breakout_bonus", 0.08))
                    pattern_notes.append(f"{fvg_type}_support")

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
                "breakout_buffer": breakout_buffer,
                "prev_range_high": prev_range_high,
                "prev_range_low": prev_range_low,
                "body_atr_ratio": body_atr_ratio,
                "pattern_evidence_notes": pattern_notes,
            },
            metadata={"strategy_code": self.strategy_code},
        )
