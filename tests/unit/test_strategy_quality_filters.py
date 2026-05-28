from __future__ import annotations

from datetime import datetime, timezone

from src.domain.enums import MarketRegimeType, SignalDirection
from src.domain.models.market_snapshot import MarketSnapshot
from src.domain.models.regime_result import RegimeResult
from src.strategies.ema_atr_trend_strategy import EmaAtrTrendStrategy
from src.strategies.range_reversion_strategy import RangeReversionStrategy
from src.strategies.volatility_breakout_strategy import VolatilityBreakoutStrategy


def _snapshot(close: float, high: float, low: float, open_price: float | None = None) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="XAUUSD",
        timeframe="M5",
        candle_time=datetime.now(timezone.utc),
        open_price=open_price if open_price is not None else close,
        high_price=high,
        low_price=low,
        close_price=close,
        tick_volume=100,
    )


def test_volatility_breakout_requires_previous_range_break() -> None:
    strategy = VolatilityBreakoutStrategy()
    snapshot = _snapshot(close=2300.5, high=2301.0, low=2299.0, open_price=2300.0)
    regime = RegimeResult(
        regime=MarketRegimeType.HIGH_VOLATILITY,
        confidence=0.8,
        is_tradeable=True,
        features={
            "atr": 1.0,
            "volatility_score": 0.03,
            "prev_range_high": 2302.0,
            "prev_range_low": 2298.0,
            "body_atr_ratio": 0.4,
        },
    )
    signal = strategy.generate_signal(snapshot, regime, {"breakout_buffer_atr": 0.15, "breakout_confirm_close": True})
    assert signal is None


def test_volatility_breakout_generates_signal_on_valid_break() -> None:
    strategy = VolatilityBreakoutStrategy()
    snapshot = _snapshot(close=2303.0, high=2303.5, low=2299.0, open_price=2302.4)
    regime = RegimeResult(
        regime=MarketRegimeType.HIGH_VOLATILITY,
        confidence=0.8,
        is_tradeable=True,
        features={
            "atr": 1.0,
            "volatility_score": 0.03,
            "prev_range_high": 2302.0,
            "prev_range_low": 2298.0,
            "body_atr_ratio": 0.45,
        },
    )
    signal = strategy.generate_signal(snapshot, regime, {"breakout_buffer_atr": 0.15, "breakout_confirm_close": True})
    assert signal is not None
    assert signal.direction == SignalDirection.BUY


def test_range_reversion_requires_boundary_touch() -> None:
    strategy = RangeReversionStrategy()
    snapshot = _snapshot(close=2300.5, high=2301.0, low=2300.0, open_price=2300.2)
    regime = RegimeResult(
        regime=MarketRegimeType.RANGING,
        confidence=0.7,
        is_tradeable=True,
        features={
            "atr": 1.0,
            "ema_slow": 2300.0,
            "range_high": 2303.0,
            "range_low": 2297.0,
            "range_mid": 2300.0,
            "range_width": 6.0,
            "body_atr_ratio": 0.3,
        },
    )
    signal = strategy.generate_signal(snapshot, regime, {"boundary_tolerance_atr": 0.2})
    assert signal is None


def test_range_reversion_generates_signal_near_boundary() -> None:
    strategy = RangeReversionStrategy()
    snapshot = _snapshot(close=2302.9, high=2303.1, low=2302.2, open_price=2302.5)
    regime = RegimeResult(
        regime=MarketRegimeType.RANGING,
        confidence=0.7,
        is_tradeable=True,
        features={
            "atr": 1.0,
            "ema_slow": 2300.0,
            "range_high": 2303.0,
            "range_low": 2297.0,
            "range_mid": 2300.0,
            "range_width": 6.0,
            "body_atr_ratio": 0.35,
        },
    )
    signal = strategy.generate_signal(snapshot, regime, {"boundary_tolerance_atr": 0.2})
    assert signal is not None
    assert signal.direction == SignalDirection.SELL


def test_ema_trend_requires_pullback_and_confirmation() -> None:
    strategy = EmaAtrTrendStrategy()
    snapshot = _snapshot(close=2305.0, high=2306.0, low=2304.0, open_price=2304.8)
    regime = RegimeResult(
        regime=MarketRegimeType.TRENDING_BULLISH,
        confidence=0.8,
        is_tradeable=True,
        features={
            "atr": 1.0,
            "trend_strength": 1.5,
            "pullback_distance_to_ema_fast_atr": 1.5,
            "pullback_touched_ema_fast": False,
            "body_atr_ratio": 0.4,
            "confirmation_bullish": True,
        },
    )
    signal = strategy.generate_signal(snapshot, regime, {})
    assert signal is None


def test_ema_trend_generates_signal_with_valid_confirmation() -> None:
    strategy = EmaAtrTrendStrategy()
    snapshot = _snapshot(close=2301.5, high=2302.2, low=2299.8, open_price=2301.0)
    regime = RegimeResult(
        regime=MarketRegimeType.TRENDING_BULLISH,
        confidence=0.85,
        is_tradeable=True,
        features={
            "atr": 1.0,
            "trend_strength": 1.6,
            "pullback_distance_to_ema_fast_atr": 0.4,
            "pullback_touched_ema_fast": True,
            "body_atr_ratio": 0.35,
            "confirmation_bullish": True,
        },
    )
    signal = strategy.generate_signal(snapshot, regime, {})
    assert signal is not None
    assert signal.direction == SignalDirection.BUY
