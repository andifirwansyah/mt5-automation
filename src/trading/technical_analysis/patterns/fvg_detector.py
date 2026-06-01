"""Fair Value Gap detector."""

from __future__ import annotations

from typing import Any

from src.trading.technical_analysis.config import FVGConfig
from src.trading.technical_analysis.models import FVG


def _filled_percent_bullish(low: float, high: float, latest_low: float) -> float:
    gap = max(high - low, 1e-8)
    penetration = max(0.0, high - latest_low)
    return max(0.0, min(100.0, (penetration / gap) * 100.0))


def _filled_percent_bearish(low: float, high: float, latest_high: float) -> float:
    gap = max(high - low, 1e-8)
    penetration = max(0.0, latest_high - low)
    return max(0.0, min(100.0, (penetration / gap) * 100.0))


def detect_fvgs(
    candles: list[dict[str, Any]],
    atr: float,
    timeframe: str,
    config: FVGConfig,
) -> list[FVG]:
    """Detect bullish/bearish FVG and classify open/partial/filled."""

    if not config.enabled or len(candles) < 3:
        return []

    latest = candles[-1]
    latest_high = float(latest.get("high", 0.0))
    latest_low = float(latest.get("low", 0.0))
    latest_open = float(latest.get("open", 0.0))
    latest_close = float(latest.get("close", 0.0))
    latest_body = abs(latest_close - latest_open)

    min_gap = max(0.0, atr * float(config.min_fvg_size_atr))
    preferred_body = max(0.0, atr * float(config.prefer_impulse_body_atr))

    results: list[FVG] = []
    start = max(2, len(candles) - config.max_fvg_age_bars - 2)
    for i in range(start, len(candles)):
        if i - 2 < 0:
            continue
        c0 = candles[i - 2]
        c2 = candles[i]

        c0_high = float(c0.get("high", 0.0))
        c0_low = float(c0.get("low", 0.0))
        c2_high = float(c2.get("high", 0.0))
        c2_low = float(c2.get("low", 0.0))

        # bullish FVG
        if c0_high < c2_low:
            low = c0_high
            high = c2_low
            size = high - low
            if size < min_gap and not config.allow_small_fvg_as_low_confidence:
                continue
            if config.require_impulse_body and latest_body < preferred_body:
                continue

            filled_percent = _filled_percent_bullish(low=low, high=high, latest_low=latest_low)
            status = "open"
            if filled_percent >= float(config.mark_filled_when_percent_above):
                status = "filled"
            elif filled_percent > 0:
                status = "partial"

            confidence = max(config.min_confidence, min(0.95, (size / max(atr, 1e-8)) * 0.6))
            if size < min_gap:
                confidence = min(confidence, 0.45)

            results.append(
                FVG(
                    type="bullish_fvg",
                    low=low,
                    high=high,
                    midpoint=(low + high) / 2.0,
                    status=status,
                    age_bars=len(candles) - 1 - i,
                    filled_percent=filled_percent,
                    confidence=confidence,
                    timeframe=timeframe,
                    created_index=i,
                )
            )

        # bearish FVG
        if c0_low > c2_high:
            low = c2_high
            high = c0_low
            size = high - low
            if size < min_gap and not config.allow_small_fvg_as_low_confidence:
                continue
            if config.require_impulse_body and latest_body < preferred_body:
                continue

            filled_percent = _filled_percent_bearish(low=low, high=high, latest_high=latest_high)
            status = "open"
            if filled_percent >= float(config.mark_filled_when_percent_above):
                status = "filled"
            elif filled_percent > 0:
                status = "partial"

            confidence = max(config.min_confidence, min(0.95, (size / max(atr, 1e-8)) * 0.6))
            if size < min_gap:
                confidence = min(confidence, 0.45)

            results.append(
                FVG(
                    type="bearish_fvg",
                    low=low,
                    high=high,
                    midpoint=(low + high) / 2.0,
                    status=status,
                    age_bars=len(candles) - 1 - i,
                    filled_percent=filled_percent,
                    confidence=confidence,
                    timeframe=timeframe,
                    created_index=i,
                )
            )

    return results
