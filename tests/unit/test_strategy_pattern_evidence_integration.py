from __future__ import annotations

from datetime import datetime, timezone

from src.domain.enums import MarketRegimeType, SignalDirection
from src.domain.models.market_snapshot import MarketSnapshot
from src.domain.models.regime_result import RegimeResult
from src.strategies.ema_atr_trend_strategy import EmaAtrTrendStrategy
from src.strategies.liquidity_sweep_reversal import LiquiditySweepReversalStrategy
from src.strategies.range_reversion_strategy import RangeReversionStrategy
from src.strategies.volatility_breakout_strategy import VolatilityBreakoutStrategy
from src.trading.technical_analysis.models import FVG, PatternEvidence, TechnicalAnalysisResult


def _snapshot(close: float, high: float, low: float, open_price: float) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="XAUUSD",
        timeframe="M5",
        candle_time=datetime.now(timezone.utc),
        open_price=open_price,
        high_price=high,
        low_price=low,
        close_price=close,
        tick_volume=200,
    )


def _ta_with_double_bottom_and_bullish_fvg() -> TechnicalAnalysisResult:
    fvg = FVG(
        type="bullish_fvg",
        low=2300.0,
        high=2301.0,
        midpoint=2300.5,
        status="open",
        age_bars=2,
        filled_percent=0.0,
        confidence=0.5,
        timeframe="M5",
        created_index=10,
    )
    return TechnicalAnalysisResult(
        symbol="XAUUSD",
        timeframe="M5",
        bias="buy",
        technical_score=0.6,
        buy_score=0.6,
        sell_score=0.1,
        pattern_evidence=[
            PatternEvidence(
                pattern_type="DOUBLE_BOTTOM",
                signal="buy",
                confidence=0.8,
                details={"status": "neckline_broken"},
            ),
            PatternEvidence(
                pattern_type="FVG",
                signal="buy",
                confidence=0.5,
                fvgs=[fvg],
                details={"status": "open"},
            ),
        ],
        warnings=[],
        strategy_hints=[],
        conflict_flags=[],
        metadata={},
    )


def test_volatility_breakout_pattern_enabled_adds_bonus_vs_disabled() -> None:
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
    ta = _ta_with_double_bottom_and_bullish_fvg()

    base_cfg = {"breakout_buffer_atr": 0.15, "breakout_confirm_close": True}
    no_pattern_signal = strategy.generate_signal(snapshot, regime, base_cfg, technical_analysis=ta)
    with_pattern_signal = strategy.generate_signal(
        snapshot,
        regime,
        {
            **base_cfg,
            "pattern_evidence": {
                "enabled": True,
                "allow_double_bottom_neckline_break": True,
                "fvg_confirmation_enabled": True,
                "neckline_break_bonus": 0.12,
                "fvg_after_breakout_bonus": 0.08,
                "use_as_hard_requirement": False,
            },
        },
        technical_analysis=ta,
    )
    assert no_pattern_signal is not None and with_pattern_signal is not None
    assert with_pattern_signal.confidence > no_pattern_signal.confidence


def test_range_reversion_pattern_toggle_changes_confidence() -> None:
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
    ta = TechnicalAnalysisResult(
        symbol="XAUUSD",
        timeframe="M5",
        bias="sell",
        technical_score=0.6,
        buy_score=0.1,
        sell_score=0.6,
        pattern_evidence=[PatternEvidence(pattern_type="DOUBLE_TOP", signal="sell", confidence=0.8, details={"status": "neckline_broken"})],
        warnings=[],
        strategy_hints=[],
        conflict_flags=[],
        metadata={},
    )

    base_signal = strategy.generate_signal(snapshot, regime, {"boundary_tolerance_atr": 0.2}, technical_analysis=ta)
    boosted_signal = strategy.generate_signal(
        snapshot,
        regime,
        {
            "boundary_tolerance_atr": 0.2,
            "pattern_evidence": {
                "enabled": True,
                "double_top_enabled": True,
                "require_neckline_break": False,
                "double_top_bonus": 0.16,
                "neckline_break_bonus": 0.12,
                "use_as_hard_requirement": False,
            },
        },
        technical_analysis=ta,
    )
    assert base_signal is not None and boosted_signal is not None
    assert boosted_signal.confidence > base_signal.confidence


def test_ema_trend_pattern_penalty_can_reduce_confidence() -> None:
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
    ta = TechnicalAnalysisResult(
        symbol="XAUUSD",
        timeframe="M5",
        bias="neutral",
        technical_score=0.5,
        buy_score=0.5,
        sell_score=0.4,
        pattern_evidence=[PatternEvidence(pattern_type="DOUBLE_TOP", signal="sell", confidence=0.8, details={"status": "waiting_neckline_break"})],
        warnings=[],
        strategy_hints=[],
        conflict_flags=[],
        metadata={},
    )

    base_signal = strategy.generate_signal(snapshot, regime, {}, technical_analysis=ta)
    penalized_signal = strategy.generate_signal(
        snapshot,
        regime,
        {
            "pattern_evidence": {
                "enabled": True,
                "fvg_retest_enabled": False,
                "active_reversal_pattern_penalty": -0.15,
                "block_buy_on_active_double_top": False,
            }
        },
        technical_analysis=ta,
    )
    assert base_signal is not None and penalized_signal is not None
    assert penalized_signal.confidence < base_signal.confidence


def test_liquidity_strategy_pattern_adjustment_enabled_vs_disabled() -> None:
    strategy = LiquiditySweepReversalStrategy()
    ta = _ta_with_double_bottom_and_bullish_fvg()

    base_conf, _ = strategy._apply_pattern_evidence_adjustment(
        signal_confidence=0.70,
        sweep={"direction": SignalDirection.SELL},
        technical_analysis=ta,
        config={"pattern_evidence": {"enabled": False}},
    )
    boosted_conf, _ = strategy._apply_pattern_evidence_adjustment(
        signal_confidence=0.70,
        sweep={"direction": SignalDirection.SELL},
        technical_analysis=ta,
        config={
            "pattern_evidence": {
                "enabled": True,
                "allow_double_bottom_after_low_sweep": True,
                "require_neckline_break": False,
                "fvg_after_sweep_bonus": 0.10,
                "neckline_break_bonus": 0.12,
                "use_as_hard_requirement": False,
            }
        },
    )
    assert boosted_conf > base_conf
