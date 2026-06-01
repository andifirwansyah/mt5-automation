"""Double bottom detector based on swing lows/highs and neckline logic."""

from __future__ import annotations

from typing import Any

from src.trading.technical_analysis.config import DoubleBottomConfig, NecklineBreakConfig
from src.trading.technical_analysis.models import DoubleBottomPattern, SwingPoint
from src.trading.technical_analysis.patterns.neckline_validator import validate_neckline_break


def detect_double_bottom_pattern(
    candles: list[dict[str, Any]],
    swing_highs: list[SwingPoint],
    swing_lows: list[SwingPoint],
    atr: float,
    config: DoubleBottomConfig,
    neckline_config: NecklineBreakConfig,
) -> DoubleBottomPattern | None:
    """Detect double bottom pattern and optionally confirm neckline break."""

    if not config.enabled:
        return None
    if len(swing_lows) < 2:
        return None

    max_distance = max(0.0, atr * float(config.max_bottom_distance_atr))
    min_depth = max(0.0, atr * float(config.min_neckline_depth_atr))

    selected: tuple[SwingPoint, SwingPoint, float] | None = None
    for i in range(len(swing_lows) - 1, 0, -1):
        left_bottom = swing_lows[i - 1]
        right_bottom = swing_lows[i]
        bars_between = right_bottom.index - left_bottom.index

        if bars_between < int(config.min_bars_between_bottoms):
            continue
        if bars_between > int(config.max_bars_between_bottoms):
            continue
        if abs(left_bottom.price - right_bottom.price) > max_distance:
            continue

        middle_highs = [p for p in swing_highs if left_bottom.index < p.index < right_bottom.index]
        if not middle_highs:
            continue

        neckline_point = max(middle_highs, key=lambda p: p.price)
        depth = neckline_point.price - max(left_bottom.price, right_bottom.price)
        if depth < min_depth:
            continue

        selected = (left_bottom, right_bottom, neckline_point.price)
        break

    if selected is None:
        return None

    left_bottom, right_bottom, neckline = selected
    latest = candles[-1] if candles else {}
    break_eval = validate_neckline_break(
        latest_candle=latest,
        neckline=neckline,
        direction="buy",
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

    return DoubleBottomPattern(
        left_bottom=left_bottom,
        right_bottom=right_bottom,
        neckline=neckline,
        is_neckline_broken=bool(break_eval["is_broken"]),
        confidence=confidence,
        status=status,
        warnings=list(break_eval["warnings"]),
        rejection_reason=None,
        details={
            "break_eval": break_eval["details"],
            "bars_between_bottoms": right_bottom.index - left_bottom.index,
            "bottom_distance": abs(left_bottom.price - right_bottom.price),
        },
    )
