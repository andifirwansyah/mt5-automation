"""Neckline break validator for double top/bottom patterns."""

from __future__ import annotations

from typing import Any, Literal

from src.trading.technical_analysis.config import NecklineBreakConfig


def validate_neckline_break(
    latest_candle: dict[str, Any],
    neckline: float,
    direction: Literal["sell", "buy"],
    atr: float,
    config: NecklineBreakConfig,
) -> dict[str, Any]:
    """Validate neckline break with ATR buffer and candle body preference."""

    open_price = float(latest_candle.get("open", 0.0))
    close_price = float(latest_candle.get("close", 0.0))
    high_price = float(latest_candle.get("high", close_price))
    low_price = float(latest_candle.get("low", close_price))

    buffer = max(0.0, atr * float(config.break_buffer_atr))
    min_body = max(0.0, atr * float(config.min_break_body_atr))
    body_size = abs(close_price - open_price)
    body_ok = body_size >= min_body

    if direction == "sell":
        broken = close_price < (neckline - buffer) if config.require_candle_close else low_price < (neckline - buffer)
    else:
        broken = close_price > (neckline + buffer) if config.require_candle_close else high_price > (neckline + buffer)

    warnings: list[str] = []
    status = "waiting_neckline_break"
    if broken and body_ok:
        status = "neckline_broken"
    elif broken and not body_ok:
        if config.allow_weak_break_as_warning:
            status = "weak_neckline_break"
            warnings.append("Break candle body below preferred ATR threshold")
        else:
            status = "waiting_neckline_break"

    return {
        "status": status,
        "is_broken": bool(status == "neckline_broken"),
        "is_weak_break": bool(status == "weak_neckline_break"),
        "warnings": warnings,
        "details": {
            "direction": direction,
            "neckline": neckline,
            "buffer": buffer,
            "open": open_price,
            "close": close_price,
            "body_size": body_size,
            "min_body": min_body,
        },
    }
