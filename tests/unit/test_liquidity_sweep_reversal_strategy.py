"""Unit tests untuk Liquidity Sweep Reversal Strategy yang kompatibel dengan project."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.domain.enums import MarketRegimeType, SignalDirection
from src.domain.models.market_snapshot import MarketSnapshot
from src.domain.models.regime_result import RegimeResult
from src.strategies.liquidity_sweep_reversal import LiquiditySweepReversalStrategy


def _snapshot(open_price: float = 100.0, high: float = 102.0, low: float = 99.0, close: float = 101.0, tick_volume: int = 1000):
    snap = MagicMock(spec=MarketSnapshot)
    snap.open_price = open_price
    snap.high_price = high
    snap.low_price = low
    snap.close_price = close
    snap.tick_volume = tick_volume
    return snap


def _regime(regime_type: MarketRegimeType = MarketRegimeType.HIGH_VOLATILITY, volatility_score: float = 0.7, atr: float = 1.0):
    rg = MagicMock(spec=RegimeResult)
    rg.regime = regime_type
    rg.features = {"volatility_score": volatility_score, "atr": atr, "avg_volume": 900}
    return rg


def test_import_and_default_config_work() -> None:
    strategy = LiquiditySweepReversalStrategy()
    assert strategy.strategy_code == "LIQUIDITY_SWEEP_REVERSAL"


def test_validate_inputs_accepts_valid_data() -> None:
    strategy = LiquiditySweepReversalStrategy()
    assert strategy._validate_inputs(_snapshot(), _regime(), {}) is True


def test_validate_inputs_rejects_zero_tick_volume() -> None:
    strategy = LiquiditySweepReversalStrategy()
    assert strategy._validate_inputs(_snapshot(tick_volume=0), _regime(), {}) is False


def test_validate_market_regime_accepts_high_volatility() -> None:
    strategy = LiquiditySweepReversalStrategy()
    cfg = {"allowed_regimes": [MarketRegimeType.HIGH_VOLATILITY], "min_volatility_score": 0.5}
    assert strategy._validate_market_regime(_regime(MarketRegimeType.HIGH_VOLATILITY, 0.8), cfg) is True


def test_validate_market_regime_rejects_disallowed_regime() -> None:
    strategy = LiquiditySweepReversalStrategy()
    cfg = {"allowed_regimes": [MarketRegimeType.HIGH_VOLATILITY], "min_volatility_score": 0.5}
    assert strategy._validate_market_regime(_regime(MarketRegimeType.CHOPPY, 0.8), cfg) is False


def test_detect_downside_sweep() -> None:
    strategy = LiquiditySweepReversalStrategy()
    snapshot = _snapshot(low=98.6, tick_volume=1400)
    regime = _regime(volatility_score=0.8)
    levels = {"supports": [99.0], "resistances": [102.0]}
    sweep = strategy._detect_liquidity_sweep(snapshot, regime, levels, atr=1.0, config={"sweep_extension_atr": 0.3, "level_tolerance_atr": 0.15})
    assert sweep is not None
    assert sweep["direction"] == SignalDirection.SELL


def test_detect_upside_sweep() -> None:
    strategy = LiquiditySweepReversalStrategy()
    snapshot = _snapshot(high=102.4, tick_volume=1400)
    regime = _regime(volatility_score=0.8)
    levels = {"supports": [98.0], "resistances": [102.0]}
    sweep = strategy._detect_liquidity_sweep(snapshot, regime, levels, atr=1.0, config={"sweep_extension_atr": 0.3, "level_tolerance_atr": 0.15})
    assert sweep is not None
    assert sweep["direction"] == SignalDirection.BUY


def test_reversal_analysis_requires_correct_direction() -> None:
    strategy = LiquiditySweepReversalStrategy()
    snapshot = _snapshot(open_price=99.0, close=100.5, high=101.0, low=98.5)
    regime = _regime()
    wrong_sweep = {"direction": SignalDirection.BUY, "level": 101.0, "confidence": 0.8, "volume_quality": 0.8}
    out = strategy._analyze_reversal_pattern(snapshot, regime, wrong_sweep, atr=1.0, config={"reversal_candle_body_atr": 0.3, "reversal_wick_ratio": 1.8})
    assert out is None


def test_risk_reward_validation() -> None:
    strategy = LiquiditySweepReversalStrategy()
    ok = strategy._validate_risk_reward({"entry_price": 100, "stop_loss": 98, "take_profit": 104}, {"risk_reward_ratio_min": 1.5})
    bad = strategy._validate_risk_reward({"entry_price": 100, "stop_loss": 98, "take_profit": 101}, {"risk_reward_ratio_min": 1.5})
    assert ok is True
    assert bad is False
