"""Double top detector based on swing highs/lows and neckline logic."""

from __future__ import annotations

from typing import Any

from src.trading.technical_analysis.config import DoubleTopConfig, NecklineBreakConfig
from src.trading.technical_analysis.models import DoubleTopPattern, SwingPoint
from src.trading.technical_analysis.patterns.neckline_validator import validate_neckline_break


def detect_double_top_pattern(
    candles: list[dict[str, Any]],
    swing_highs: list[SwingPoint],
    swing_lows: list[SwingPoint],
    atr: float,
    config: DoubleTopConfig,
    neckline_config: NecklineBreakConfig,
) -> DoubleTopPattern | None:
    """Detect double top pattern and optionally confirm neckline break."""

    if not config.enabled:
        return None
    if len(swing_highs) < 2:
        return None

    max_distance = max(0.0, atr * float(config.max_top_distance_atr))
    min_depth = max(0.0, atr * float(config.min_neckline_depth_atr))

    selected: tuple[SwingPoint, SwingPoint, float] | None = None
    for i in range(len(swing_highs) - 1, 0, -1):
        left_peak = swing_highs[i - 1]
        right_peak = swing_highs[i]
        bars_between = right_peak.index - left_peak.index

        if bars_between < int(config.min_bars_between_tops):
            continue
        if bars_between > int(config.max_bars_between_tops):
            continue
        if abs(left_peak.price - right_peak.price) > max_distance:
            continue

        middle_lows = [p for p in swing_lows if left_peak.index < p.index < right_peak.index]
        if not middle_lows:
            continue

        neckline_point = min(middle_lows, key=lambda p: p.price)
        depth = min(left_peak.price, right_peak.price) - neckline_point.price
        if depth < min_depth:
            continue

        selected = (left_peak, right_peak, neckline_point.price)
        break

    if selected is None:
        return None

    left_peak, right_peak, neckline = selected
    latest = candles[-1] if candles else {}
    break_eval = validate_neckline_break(
        latest_candle=latest,
        neckline=neckline,
        direction="sell",
        atr=atr,
        config=neckline_config,
    )

    status = str(break_eval["status"])
    if not break_eval["is_broken"] and not break_eval["is_weak_break"]:
        status = "waiting_neckline_break"
    if config.require_neckline_break and status != "neckline_broken":
        status = "waiting_neckline_break"

    confidence = 0.55
    confidence += 0.1 if status in ("waiting_neckline_break", "weak_neckline_break", "neckline_broken") else 0.0
    confidence += 0.15 if status == "neckline_broken" else 0.0
    confidence = max(0.0, min(1.0, confidence))

    return DoubleTopPattern(
        left_peak=left_peak,
        right_peak=right_peak,
        neckline=neckline,
        is_neckline_broken=bool(break_eval["is_broken"]),
        confidence=confidence,
        status=status,
        warnings=list(break_eval["warnings"]),
        rejection_reason=None,
        details={
            "break_eval": break_eval["details"],
            "bars_between_tops": right_peak.index - left_peak.index,
            "top_distance": abs(left_peak.price - right_peak.price),
        },
    )
