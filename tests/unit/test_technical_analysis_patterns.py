from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.domain.enums import MarketRegimeType
from src.domain.models.regime_result import RegimeResult
from src.pipeline.trading_context import TradingContext
from src.trading.technical_analysis.config import FVGConfig, NecklineBreakConfig, TechnicalAnalysisConfig
from src.trading.technical_analysis.engine import TechnicalAnalysisEngine
from src.trading.technical_analysis.patterns.double_bottom_detector import detect_double_bottom_pattern
from src.trading.technical_analysis.patterns.double_top_detector import detect_double_top_pattern
from src.trading.technical_analysis.patterns.fvg_detector import detect_fvgs
from src.trading.technical_analysis.patterns.neckline_validator import validate_neckline_break
from src.trading.technical_analysis.patterns.swing_detector import detect_swing_points


def _make_context() -> TradingContext:
    return TradingContext.from_candle_event(
        {
            "symbol": "XAUUSD",
            "timeframe": "M5",
            "candle_time": datetime.now(timezone.utc).isoformat(),
            "open": 2300.0,
            "high": 2302.0,
            "low": 2299.0,
            "close": 2301.0,
            "tick_volume": 111,
        }
    )


def _double_top_rows() -> list[dict]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    data = [
        (100.0, 101.0, 99.5, 100.4),
        (100.5, 101.2, 100.0, 100.7),
        (101.0, 102.0, 100.6, 101.5),
        (101.6, 103.0, 101.3, 102.2),
        (102.4, 104.0, 102.0, 103.5),
        (108.5, 110.0, 108.0, 109.1),
        (108.2, 108.5, 107.8, 108.1),
        (107.9, 108.2, 107.5, 107.7),
        (107.6, 107.9, 107.2, 107.4),
        (107.3, 108.0, 107.0, 107.2),
        (107.5, 108.2, 107.4, 108.0),
        (108.2, 109.0, 108.0, 108.8),
        (109.0, 109.95, 108.9, 109.2),
        (108.4, 108.8, 108.0, 108.1),
        (108.1, 108.4, 107.8, 108.0),
        (107.9, 108.2, 107.6, 107.8),
        (107.8, 108.0, 107.5, 107.7),
        (107.6, 107.9, 107.2, 107.4),
        (107.4, 107.6, 107.0, 107.1),
        (107.3, 107.5, 106.5, 106.7),
    ]
    rows: list[dict] = []
    for i, (open_price, high, low, close) in enumerate(data):
        rows.append(
            {
                "time": now - timedelta(minutes=(len(data) - i) * 5),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "tick_volume": 100 + i,
            }
        )
    return rows


def _double_bottom_rows() -> list[dict]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    data = [
        (110.0, 110.8, 109.5, 110.2),
        (109.8, 110.3, 109.3, 109.6),
        (109.4, 109.8, 108.9, 109.1),
        (109.0, 109.3, 108.5, 108.8),
        (108.6, 108.9, 108.0, 108.2),
        (106.8, 107.2, 106.0, 106.4),
        (106.7, 107.1, 106.3, 106.8),
        (107.0, 107.4, 106.6, 107.2),
        (107.4, 107.8, 107.0, 107.6),
        (107.6, 109.0, 107.5, 108.7),
        (107.8, 108.4, 107.4, 108.1),
        (107.0, 107.3, 106.5, 106.8),
        (106.6, 106.95, 106.05, 106.5),
        (107.2, 107.8, 106.9, 107.5),
        (107.7, 108.1, 107.4, 107.9),
        (108.0, 108.4, 107.8, 108.2),
        (108.3, 108.8, 108.2, 108.6),
        (108.7, 109.2, 108.5, 109.0),
        (109.1, 109.5, 108.8, 109.3),
        (109.0, 109.8, 108.9, 109.6),
    ]
    rows: list[dict] = []
    for i, (open_price, high, low, close) in enumerate(data):
        rows.append(
            {
                "time": now - timedelta(minutes=(len(data) - i) * 5),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "tick_volume": 100 + i,
            }
        )
    return rows


def test_swing_detector_detects_high_and_low_points() -> None:
    candles = _double_top_rows()
    highs, lows = detect_swing_points(candles, left_bars=1, right_bars=1, atr=1.0, min_distance_atr=0.0)
    assert len(highs) >= 2
    assert len(lows) >= 1


def test_double_top_detector_detects_pattern_with_neckline_break() -> None:
    candles = _double_top_rows()
    highs, lows = detect_swing_points(candles, left_bars=1, right_bars=1, atr=1.0, min_distance_atr=0.0)
    pattern = detect_double_top_pattern(
        candles=candles,
        swing_highs=highs,
        swing_lows=lows,
        atr=1.0,
        config=TechnicalAnalysisConfig().double_top,
        neckline_config=TechnicalAnalysisConfig().neckline_break,
    )
    assert pattern is not None
    assert pattern.status in ("neckline_broken", "weak_neckline_break", "waiting_neckline_break")


def test_double_bottom_detector_detects_pattern_with_neckline_break() -> None:
    candles = _double_bottom_rows()
    highs, lows = detect_swing_points(candles, left_bars=1, right_bars=1, atr=1.0, min_distance_atr=0.0)
    pattern = detect_double_bottom_pattern(
        candles=candles,
        swing_highs=highs,
        swing_lows=lows,
        atr=1.0,
        config=TechnicalAnalysisConfig().double_bottom,
        neckline_config=TechnicalAnalysisConfig().neckline_break,
    )
    assert pattern is not None
    assert pattern.status in ("neckline_broken", "weak_neckline_break", "waiting_neckline_break")


def test_neckline_break_validator_marks_weak_break_as_warning() -> None:
    result = validate_neckline_break(
        latest_candle={"open": 108.0, "close": 107.85, "high": 108.1, "low": 107.7},
        neckline=108.0,
        direction="sell",
        atr=1.0,
        config=NecklineBreakConfig(break_buffer_atr=0.08, min_break_body_atr=0.5, allow_weak_break_as_warning=True),
    )
    assert result["status"] == "weak_neckline_break"
    assert len(result["warnings"]) >= 1


def test_technical_analysis_engine_generates_pattern_evidence() -> None:
    context = _make_context()
    context.regime_result = RegimeResult(
        regime=MarketRegimeType.HIGH_VOLATILITY,
        confidence=0.8,
        is_tradeable=True,
        features={"atr": 1.0},
    )
    context.ingestion_result = {"rates_by_timeframe": {"M5": _double_top_rows()}}

    config = TechnicalAnalysisConfig(min_candles_required=10)
    config.swing.left_bars = 1
    config.swing.right_bars = 1
    config.swing.min_distance_atr = 0.0

    result = TechnicalAnalysisEngine(config=config).run(context)

    assert result.rejected is False
    assert result.technical_analysis is not None
    assert len(result.technical_analysis.pattern_evidence) >= 1


def test_fvg_detector_detects_bullish_and_bearish_fvg() -> None:
    candles = [
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
        {"open": 100.5, "high": 101.5, "low": 100.2, "close": 101.2},
        {"open": 102.0, "high": 103.0, "low": 102.2, "close": 102.8},  # bullish fvg vs candle0
        {"open": 102.7, "high": 103.0, "low": 102.4, "close": 102.6},
        {"open": 99.8, "high": 100.2, "low": 99.1, "close": 99.4},      # bearish fvg vs candle2
    ]
    fvgs = detect_fvgs(candles=candles, atr=1.0, timeframe="M5", config=FVGConfig())
    assert any(f.type == "bullish_fvg" for f in fvgs)
    assert any(f.type == "bearish_fvg" for f in fvgs)


def test_fvg_detector_handles_small_gap_as_low_confidence() -> None:
    candles = [
        {"open": 100.0, "high": 101.0, "low": 99.8, "close": 100.6},
        {"open": 100.6, "high": 101.1, "low": 100.2, "close": 100.9},
        {"open": 101.02, "high": 101.2, "low": 101.03, "close": 101.1},
    ]
    cfg = FVGConfig(min_fvg_size_atr=0.2, allow_small_fvg_as_low_confidence=True)
    fvgs = detect_fvgs(candles=candles, atr=1.0, timeframe="M5", config=cfg)
    assert len(fvgs) >= 1
    assert all(f.confidence <= 0.45 for f in fvgs)


def test_fvg_status_open_partial_filled() -> None:
    candles = [
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.2},
        {"open": 100.2, "high": 101.2, "low": 100.0, "close": 100.8},
        {"open": 102.0, "high": 103.0, "low": 102.5, "close": 102.8},
    ]
    cfg = FVGConfig(mark_filled_when_percent_above=80)

    open_fvgs = detect_fvgs(candles=candles, atr=1.0, timeframe="M5", config=cfg)
    assert any(f.status == "open" for f in open_fvgs)

    candles_partial = candles + [{"open": 102.3, "high": 102.6, "low": 101.6, "close": 101.9}]
    partial_fvgs = detect_fvgs(candles=candles_partial, atr=1.0, timeframe="M5", config=cfg)
    assert any(f.status in ("partial", "filled") for f in partial_fvgs)

    candles_filled = candles + [{"open": 101.8, "high": 102.1, "low": 100.8, "close": 101.0}]
    filled_fvgs = detect_fvgs(candles=candles_filled, atr=1.0, timeframe="M5", config=cfg)
    assert any(f.status == "filled" for f in filled_fvgs)


def test_technical_analysis_engine_includes_fvg_evidence() -> None:
    context = _make_context()
    context.regime_result = RegimeResult(
        regime=MarketRegimeType.TRENDING_BULLISH,
        confidence=0.7,
        is_tradeable=True,
        features={"atr": 1.0},
    )
    rows = [
        {"time": datetime.now(timezone.utc), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "tick_volume": 1},
        {"time": datetime.now(timezone.utc), "open": 100.5, "high": 101.5, "low": 100.2, "close": 101.2, "tick_volume": 1},
        {"time": datetime.now(timezone.utc), "open": 102.0, "high": 103.0, "low": 102.2, "close": 102.8, "tick_volume": 1},
        {"time": datetime.now(timezone.utc), "open": 102.7, "high": 103.1, "low": 102.4, "close": 102.9, "tick_volume": 1},
        {"time": datetime.now(timezone.utc), "open": 102.8, "high": 103.2, "low": 102.6, "close": 103.0, "tick_volume": 1},
        {"time": datetime.now(timezone.utc), "open": 102.9, "high": 103.3, "low": 102.7, "close": 103.1, "tick_volume": 1},
        {"time": datetime.now(timezone.utc), "open": 103.0, "high": 103.4, "low": 102.8, "close": 103.2, "tick_volume": 1},
        {"time": datetime.now(timezone.utc), "open": 103.1, "high": 103.5, "low": 102.9, "close": 103.3, "tick_volume": 1},
        {"time": datetime.now(timezone.utc), "open": 103.2, "high": 103.6, "low": 103.0, "close": 103.4, "tick_volume": 1},
        {"time": datetime.now(timezone.utc), "open": 103.3, "high": 103.7, "low": 103.1, "close": 103.5, "tick_volume": 1},
    ]
    context.ingestion_result = {"rates_by_timeframe": {"M5": rows}}

    cfg = TechnicalAnalysisConfig(min_candles_required=5)
    cfg.swing.left_bars = 1
    cfg.swing.right_bars = 1
    result = TechnicalAnalysisEngine(config=cfg).run(context)
    assert result.technical_analysis is not None
    assert any(e.pattern_type == "FVG" for e in result.technical_analysis.pattern_evidence)
