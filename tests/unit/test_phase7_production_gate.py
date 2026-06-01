from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.domain.enums import MarketRegimeType, SignalDirection
from src.domain.models.market_snapshot import MarketSnapshot
from src.domain.models.regime_result import RegimeResult
from src.engines.strategy_selector import StrategySelector
from src.pipeline.trading_context import TradingContext
from src.pipeline.trading_pipeline import PIPELINE_STEP_ORDER
from src.strategies.ema_atr_trend_strategy import EmaAtrTrendStrategy
from src.strategies.liquidity_sweep_reversal import LiquiditySweepReversalStrategy
from src.strategies.range_reversion_strategy import RangeReversionStrategy
from src.strategies.volatility_breakout_strategy import VolatilityBreakoutStrategy
from src.trading.technical_analysis.config import FVGConfig, TechnicalAnalysisConfig
from src.trading.technical_analysis.engine import TechnicalAnalysisEngine
from src.trading.technical_analysis.models import FVG, PatternEvidence, TechnicalAnalysisResult
from src.trading.technical_analysis.patterns.double_bottom_detector import detect_double_bottom_pattern
from src.trading.technical_analysis.patterns.double_top_detector import detect_double_top_pattern
from src.trading.technical_analysis.patterns.fvg_detector import detect_fvgs
from src.trading.technical_analysis.patterns.swing_detector import detect_swing_points


def _context() -> TradingContext:
    return TradingContext.from_candle_event(
        {
            "symbol": "XAUUSD",
            "timeframe": "M5",
            "candle_time": datetime.now(timezone.utc).isoformat(),
            "open": 2300.0,
            "high": 2302.0,
            "low": 2299.0,
            "close": 2301.0,
            "tick_volume": 120,
        }
    )


def _rows_for_double_top(latest_close: float = 106.7, latest_open: float = 107.3) -> list[dict]:
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
        (latest_open, 107.5, 106.5, latest_close),
    ]
    rows: list[dict] = []
    for i, (o, h, l, c) in enumerate(data):
        rows.append({"time": now - timedelta(minutes=(len(data) - i) * 5), "open": o, "high": h, "low": l, "close": c, "tick_volume": 100 + i})
    return rows


def _rows_for_double_bottom() -> list[dict]:
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
    for i, (o, h, l, c) in enumerate(data):
        rows.append({"time": now - timedelta(minutes=(len(data) - i) * 5), "open": o, "high": h, "low": l, "close": c, "tick_volume": 100 + i})
    return rows


def test_phase7_required_core_checks() -> None:
    # 1 + 2
    ctx = _context()
    assert ctx.technical_analysis is None
    assert PIPELINE_STEP_ORDER.index("MarketRegimeEngine") < PIPELINE_STEP_ORDER.index("TechnicalAnalysisEngine")

    # 3,4,5,6,7
    top_rows = _rows_for_double_top()
    highs, lows = detect_swing_points(top_rows, left_bars=1, right_bars=1, atr=1.0, min_distance_atr=0.0)
    assert len(highs) >= 2
    assert len(lows) >= 1
    top = detect_double_top_pattern(top_rows, highs, lows, 1.0, TechnicalAnalysisConfig().double_top, TechnicalAnalysisConfig().neckline_break)
    assert top is not None
    wait_top_rows = _rows_for_double_top(latest_close=107.95, latest_open=108.0)
    wh, wl = detect_swing_points(wait_top_rows, left_bars=1, right_bars=1, atr=1.0, min_distance_atr=0.0)
    wait_top = detect_double_top_pattern(wait_top_rows, wh, wl, 1.0, TechnicalAnalysisConfig().double_top, TechnicalAnalysisConfig().neckline_break)
    assert wait_top is not None and wait_top.status in ("waiting_neckline_break", "weak_neckline_break")
    assert top.status in ("neckline_broken", "weak_neckline_break", "waiting_neckline_break")

    # 8,9
    bottom_rows = _rows_for_double_bottom()
    bh, bl = detect_swing_points(bottom_rows, left_bars=1, right_bars=1, atr=1.0, min_distance_atr=0.0)
    bottom = detect_double_bottom_pattern(bottom_rows, bh, bl, 1.0, TechnicalAnalysisConfig().double_bottom, TechnicalAnalysisConfig().neckline_break)
    assert bottom is not None
    assert bottom.status in ("neckline_broken", "weak_neckline_break", "waiting_neckline_break")


def test_phase7_fvg_checks() -> None:
    # 10,11,12,13
    candles = [
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
        {"open": 100.5, "high": 101.5, "low": 100.2, "close": 101.2},
        {"open": 102.0, "high": 103.0, "low": 102.2, "close": 102.8},
        {"open": 102.7, "high": 103.0, "low": 102.4, "close": 102.6},
        {"open": 99.8, "high": 100.2, "low": 99.1, "close": 99.4},
    ]
    fvgs = detect_fvgs(candles, atr=1.0, timeframe="M5", config=FVGConfig())
    assert any(f.type == "bullish_fvg" for f in fvgs)
    assert any(f.type == "bearish_fvg" for f in fvgs)

    small_cfg = FVGConfig(min_fvg_size_atr=0.2, allow_small_fvg_as_low_confidence=True)
    tiny_gap_candles = [
        {"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.4},
        {"open": 100.4, "high": 100.9, "low": 100.0, "close": 100.5},
        {"open": 101.01, "high": 101.2, "low": 101.02, "close": 101.1},
    ]
    small_fvgs = detect_fvgs(tiny_gap_candles, atr=1.0, timeframe="M5", config=small_cfg)
    if small_fvgs:
        assert all(f.confidence <= 0.45 for f in small_fvgs)

    statuses = {f.status for f in fvgs}
    assert statuses.issubset({"open", "partial", "filled"})


def test_phase7_selector_reads_ta_hints() -> None:
    # 14
    class DummySession:
        @staticmethod
        def commit() -> None:
            return None

    class Row:
        def __init__(self, code: str):
            self.id = uuid.uuid4()
            self.code = code
            self.name = code

    class Cfg:
        config = {"lot_size": 0.01, "allow_high_volatility": True}

    class Repo:
        def __init__(self):
            self.session = DummySession()
            self.rows = [Row("VOLATILITY_BREAKOUT"), Row("LIQUIDITY_SWEEP_REVERSAL")]

        def get_active_strategies(self):
            return self.rows

        @staticmethod
        def get_active_strategy_configs(**_kwargs):
            return [Cfg()]

        @staticmethod
        def create_strategy_selection(**_kwargs):
            return None

        @staticmethod
        def get_recent_performance_by_strategy(**_kwargs):
            return []

    ctx = _context()
    ctx.ingestion_result = {"symbol_id": str(uuid.uuid4()), "timeframe_ids": {"M5": str(uuid.uuid4())}}
    ctx.regime_result = RegimeResult(regime=MarketRegimeType.HIGH_VOLATILITY, confidence=0.7, is_tradeable=True, features={})
    ctx.technical_analysis = TechnicalAnalysisResult(
        symbol="XAUUSD",
        timeframe="M5",
        bias="neutral",
        technical_score=0.5,
        buy_score=0.5,
        sell_score=0.5,
        pattern_evidence=[],
        warnings=[],
        strategy_hints=["LIQUIDITY_SWEEP_REVERSAL"],
        conflict_flags=[],
        metadata={},
    )
    out = StrategySelector(strategy_repository=Repo()).run(ctx)
    assert out.strategy_selection is not None
    assert out.strategy_selection.strategy_code == "LIQUIDITY_SWEEP_REVERSAL"


def test_phase7_backtest_hook_and_safety_tokens() -> None:
    # 19 + backtest hook
    ctx = _context()
    ctx.ingestion_result = {"rates_by_timeframe": {"M5": _rows_for_double_top()}}
    ctx.regime_result = RegimeResult(regime=MarketRegimeType.HIGH_VOLATILITY, confidence=0.8, is_tradeable=True, features={"atr": 1.0})
    cfg = TechnicalAnalysisConfig(min_candles_required=10)
    cfg.swing.left_bars = 1
    cfg.swing.right_bars = 1
    out = TechnicalAnalysisEngine(config=cfg).run(ctx)
    assert out.technical_analysis is not None

    ta_file = Path(__file__).resolve().parents[2] / "src" / "trading" / "technical_analysis" / "engine.py"
    text = ta_file.read_text(encoding="utf-8")
    assert "order_send" not in text
    assert "lot_size" not in text
    assert "ExecutionGate" not in text


def test_phase7_strategy_safe_disabled_pattern_evidence() -> None:
    # 15 + 16 simplified safe checks
    ta = TechnicalAnalysisResult(
        symbol="XAUUSD",
        timeframe="M5",
        bias="buy",
        technical_score=0.7,
        buy_score=0.7,
        sell_score=0.2,
        pattern_evidence=[PatternEvidence(pattern_type="DOUBLE_BOTTOM", signal="buy", confidence=0.8, details={"status": "neckline_broken"})],
        warnings=[],
        strategy_hints=[],
        conflict_flags=[],
        metadata={},
    )

    vb = VolatilityBreakoutStrategy()
    vb_snapshot = _snapshot(2303.0, 2303.5, 2299.0, 2302.4)
    vb_regime = RegimeResult(regime=MarketRegimeType.HIGH_VOLATILITY, confidence=0.8, is_tradeable=True, features={"atr": 1.0, "volatility_score": 0.03, "prev_range_high": 2302.0, "prev_range_low": 2298.0, "body_atr_ratio": 0.45})
    s1 = vb.generate_signal(vb_snapshot, vb_regime, {"breakout_buffer_atr": 0.15, "breakout_confirm_close": True}, technical_analysis=ta)
    s2 = vb.generate_signal(vb_snapshot, vb_regime, {"breakout_buffer_atr": 0.15, "breakout_confirm_close": True, "pattern_evidence": {"enabled": False}}, technical_analysis=ta)
    assert s1 is not None and s2 is not None

    rr = RangeReversionStrategy()
    rr_snapshot = _snapshot(2302.9, 2303.1, 2302.2, 2302.5)
    rr_regime = RegimeResult(regime=MarketRegimeType.RANGING, confidence=0.7, is_tradeable=True, features={"atr": 1.0, "ema_slow": 2300.0, "range_high": 2303.0, "range_low": 2297.0, "range_mid": 2300.0, "range_width": 6.0, "body_atr_ratio": 0.35})
    r1 = rr.generate_signal(rr_snapshot, rr_regime, {"boundary_tolerance_atr": 0.2}, technical_analysis=ta)
    r2 = rr.generate_signal(rr_snapshot, rr_regime, {"boundary_tolerance_atr": 0.2, "pattern_evidence": {"enabled": False}}, technical_analysis=ta)
    assert r1 is not None and r2 is not None

    et = EmaAtrTrendStrategy()
    et_snapshot = _snapshot(2301.5, 2302.2, 2299.8, 2301.0)
    et_regime = RegimeResult(regime=MarketRegimeType.TRENDING_BULLISH, confidence=0.85, is_tradeable=True, features={"atr": 1.0, "trend_strength": 1.6, "pullback_distance_to_ema_fast_atr": 0.4, "pullback_touched_ema_fast": True, "body_atr_ratio": 0.35, "confirmation_bullish": True})
    e1 = et.generate_signal(et_snapshot, et_regime, {}, technical_analysis=ta)
    e2 = et.generate_signal(et_snapshot, et_regime, {"pattern_evidence": {"enabled": False}}, technical_analysis=ta)
    assert e1 is not None and e2 is not None

    ls = LiquiditySweepReversalStrategy()
    base_conf, _ = ls._apply_pattern_evidence_adjustment(
        signal_confidence=0.70,
        sweep={"direction": SignalDirection.SELL},
        technical_analysis=ta,
        config={"pattern_evidence": {"enabled": False}},
    )
    boosted_conf, _ = ls._apply_pattern_evidence_adjustment(
        signal_confidence=0.70,
        sweep={"direction": SignalDirection.SELL},
        technical_analysis=ta,
        config={"pattern_evidence": {"enabled": True, "fvg_after_sweep_bonus": 0.10, "neckline_break_bonus": 0.12}},
    )
    assert boosted_conf >= base_conf


def _snapshot(close: float, high: float, low: float, open_price: float) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="XAUUSD",
        timeframe="M5",
        candle_time=datetime.now(timezone.utc),
        open_price=open_price,
        high_price=high,
        low_price=low,
        close_price=close,
        tick_volume=100,
    )
