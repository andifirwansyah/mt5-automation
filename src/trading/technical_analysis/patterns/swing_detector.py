"""Swing high/low detector for technical analysis patterns."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.trading.technical_analysis.models import SwingPoint


def _to_float(value: Any) -> float:
    return float(value)


def _to_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _append_with_min_distance(
    bucket: list[SwingPoint],
    point: SwingPoint,
    atr: float,
    min_distance_atr: float,
) -> None:
    if not bucket:
        bucket.append(point)
        return

    min_distance = max(0.0, atr * min_distance_atr)
    last = bucket[-1]
    if abs(point.price - last.price) >= min_distance:
        bucket.append(point)
        return

    if point.kind == "high" and point.price > last.price:
        bucket[-1] = point
    elif point.kind == "low" and point.price < last.price:
        bucket[-1] = point


def detect_swing_points(
    candles: list[dict[str, Any]],
    left_bars: int,
    right_bars: int,
    atr: float,
    min_distance_atr: float,
) -> tuple[list[SwingPoint], list[SwingPoint]]:
    """Detect swing highs/lows using left-right candle comparison."""

    if left_bars <= 0 or right_bars <= 0:
        raise ValueError("left_bars and right_bars must be > 0")

    n = len(candles)
    if n < left_bars + right_bars + 1:
        return [], []

    swing_highs: list[SwingPoint] = []
    swing_lows: list[SwingPoint] = []

    for i in range(left_bars, n - right_bars):
        cur = candles[i]
        cur_high = _to_float(cur.get("high", 0.0))
        cur_low = _to_float(cur.get("low", 0.0))

        left_slice = candles[i - left_bars : i]
        right_slice = candles[i + 1 : i + 1 + right_bars]

        is_swing_high = all(cur_high > _to_float(c.get("high", 0.0)) for c in left_slice + right_slice)
        is_swing_low = all(cur_low < _to_float(c.get("low", 0.0)) for c in left_slice + right_slice)

        candle_time = _to_datetime(cur.get("time"))
        if is_swing_high:
            _append_with_min_distance(
                swing_highs,
                SwingPoint(index=i, price=cur_high, kind="high", candle_time=candle_time),
                atr=atr,
                min_distance_atr=min_distance_atr,
            )
        if is_swing_low:
            _append_with_min_distance(
                swing_lows,
                SwingPoint(index=i, price=cur_low, kind="low", candle_time=candle_time),
                atr=atr,
                min_distance_atr=min_distance_atr,
            )

    return swing_highs, swing_lows
