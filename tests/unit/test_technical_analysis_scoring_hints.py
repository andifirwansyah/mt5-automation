from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.domain.enums import MarketRegimeType
from src.domain.models.regime_result import RegimeResult
from src.engines.strategy_selector import StrategySelector
from src.pipeline.trading_context import TradingContext
from src.trading.technical_analysis.models import DoubleBottomPattern, FVG, SwingPoint
from src.trading.technical_analysis.patterns.pattern_evidence_builder import build_technical_analysis_result


def test_flexible_scoring_generates_buy_bias_and_hints() -> None:
    bottom = DoubleBottomPattern(
        left_bottom=SwingPoint(index=1, price=100.0, kind="low"),
        right_bottom=SwingPoint(index=10, price=100.1, kind="low"),
        neckline=102.0,
        is_neckline_broken=True,
        confidence=0.8,
        status="neckline_broken",
    )
    fvg = FVG(
        type="bullish_fvg",
        low=101.0,
        high=101.8,
        midpoint=101.4,
        status="open",
        age_bars=2,
        filled_percent=0.0,
        confidence=0.5,
        timeframe="M5",
        created_index=12,
    )

    result = build_technical_analysis_result(
        symbol="XAUUSD",
        timeframe="M5",
        trace_id=str(uuid.uuid4()),
        double_top=None,
        double_bottom=bottom,
        fvgs=[fvg],
        regime="TRENDING_BULLISH",
        warnings=[],
    )

    assert result.buy_score > result.sell_score
    assert result.bias == "buy"
    assert "RANGE_REVERSION" in result.strategy_hints
    assert "VOLATILITY_BREAKOUT" in result.strategy_hints
    assert "EMA_ATR_TREND" in result.strategy_hints


def test_conflict_adds_warning_and_conflict_flag() -> None:
    top = DoubleBottomPattern(
        left_bottom=SwingPoint(index=1, price=100.0, kind="low"),
        right_bottom=SwingPoint(index=10, price=100.1, kind="low"),
        neckline=102.0,
        is_neckline_broken=True,
        confidence=0.8,
        status="neckline_broken",
    )
    bearish_fvg = FVG(
        type="bearish_fvg",
        low=101.0,
        high=101.8,
        midpoint=101.4,
        status="open",
        age_bars=2,
        filled_percent=0.0,
        confidence=0.5,
        timeframe="M5",
        created_index=12,
    )
    result = build_technical_analysis_result(
        symbol="XAUUSD",
        timeframe="M5",
        trace_id=str(uuid.uuid4()),
        double_top=None,
        double_bottom=top,
        fvgs=[bearish_fvg],
        regime="TRENDING_BULLISH",
    )
    assert "BEARISH_FVG_VS_DOUBLE_BOTTOM" in result.conflict_flags
    assert any("CONFLICT" in w for w in result.warnings)


def test_strategy_selector_uses_ta_hints_as_tie_breaker() -> None:
    class DummySession:
        @staticmethod
        def commit() -> None:
            return None

    class StrategyRow:
        def __init__(self, code: str) -> None:
            self.id = uuid.uuid4()
            self.code = code
            self.name = code

    class ConfigRow:
        def __init__(self) -> None:
            self.config = {"lot_size": 0.01, "allow_high_volatility": True}

    class Repo:
        def __init__(self) -> None:
            self.session = DummySession()
            self.rows = [StrategyRow("VOLATILITY_BREAKOUT"), StrategyRow("LIQUIDITY_SWEEP_REVERSAL")]

        def get_active_strategies(self):
            return self.rows

        @staticmethod
        def get_active_strategy_configs(**_kwargs):
            return [ConfigRow()]

        @staticmethod
        def create_strategy_selection(**_kwargs):
            return None

        @staticmethod
        def get_recent_performance_by_strategy(**_kwargs):
            return []

    context = TradingContext.from_candle_event(
        {
            "symbol": "XAUUSD",
            "timeframe": "M5",
            "candle_time": datetime.now(timezone.utc).isoformat(),
            "open": 1,
            "high": 2,
            "low": 0.5,
            "close": 1.5,
        }
    )
    context.ingestion_result = {"symbol_id": str(uuid.uuid4()), "timeframe_ids": {"M5": str(uuid.uuid4())}}
    context.regime_result = RegimeResult(
        regime=MarketRegimeType.HIGH_VOLATILITY,
        confidence=0.7,
        is_tradeable=True,
        features={},
    )
    context.technical_analysis = build_technical_analysis_result(
        symbol="XAUUSD",
        timeframe="M5",
        trace_id=str(context.trace_id),
        double_top=None,
        double_bottom=None,
        fvgs=[],
        warnings=[],
    )
    context.technical_analysis.strategy_hints = ["LIQUIDITY_SWEEP_REVERSAL"]

    out = StrategySelector(strategy_repository=Repo()).run(context)
    assert out.strategy_selection is not None
    assert out.strategy_selection.strategy_code == "LIQUIDITY_SWEEP_REVERSAL"
