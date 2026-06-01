from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.domain.enums import MarketRegimeType
from src.domain.models.regime_result import RegimeResult
from src.pipeline.trading_context import TradingContext
from src.pipeline.trading_pipeline import PIPELINE_STEP_ORDER
from src.trading.technical_analysis.config import TechnicalAnalysisConfig
from src.trading.technical_analysis.engine import TechnicalAnalysisEngine


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
            "tick_volume": 123,
        }
    )


def _rows(count: int) -> list[dict]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows: list[dict] = []
    for i in range(count):
        t = now - timedelta(minutes=(count - i) * 5)
        base = 2300.0 + (i * 0.1)
        rows.append(
            {
                "time": t,
                "open": base,
                "high": base + 1.0,
                "low": base - 1.0,
                "close": base + 0.2,
                "tick_volume": 100 + i,
            }
        )
    return rows


def _fvg_rows() -> list[dict]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    base = [
        (100.0, 101.0, 99.0, 100.5),
        (100.5, 101.5, 100.2, 101.2),
        (102.0, 103.0, 102.2, 102.8),
        (102.7, 103.1, 102.4, 102.9),
        (102.8, 103.2, 102.6, 103.0),
        (102.9, 103.3, 102.7, 103.1),
    ]
    rows: list[dict] = []
    for idx, (open_price, high, low, close) in enumerate(base):
        rows.append(
            {
                "time": now - timedelta(minutes=(len(base) - idx) * 15),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "tick_volume": 100 + idx,
            }
        )
    return rows


def test_trading_context_has_optional_technical_analysis_field() -> None:
    context = _context()
    assert context.technical_analysis is None


def test_technical_analysis_engine_sets_safe_neutral_when_data_insufficient() -> None:
    context = _context()
    context.ingestion_result = {"rates_by_timeframe": {"M5": _rows(5)}}

    result = TechnicalAnalysisEngine().run(context)

    assert result.rejected is False
    assert result.technical_analysis is not None
    assert result.technical_analysis.bias == "neutral"
    assert "TECHNICAL_DATA_INSUFFICIENT" in result.technical_analysis.warnings
    assert result.technical_analysis.metadata.get("trace_id") == str(result.trace_id)


def test_technical_analysis_engine_sets_neutral_foundation_when_data_enough() -> None:
    context = _context()
    context.ingestion_result = {"rates_by_timeframe": {"M5": _rows(60)}}

    result = TechnicalAnalysisEngine().run(context)

    assert result.rejected is False
    assert result.technical_analysis is not None
    assert result.technical_analysis.bias == "neutral"
    assert result.technical_analysis.warnings == []
    assert result.technical_analysis.metadata.get("mode") == "pattern_evaluation"


def test_pipeline_order_places_technical_analysis_after_regime_before_selector() -> None:
    regime_idx = PIPELINE_STEP_ORDER.index("MarketRegimeEngine")
    technical_idx = PIPELINE_STEP_ORDER.index("TechnicalAnalysisEngine")
    selector_idx = PIPELINE_STEP_ORDER.index("StrategySelector")

    assert regime_idx < technical_idx < selector_idx


def test_technical_analysis_engine_uses_htf_confirmation_when_available() -> None:
    context = _context()
    context.regime_result = RegimeResult(
        regime=MarketRegimeType.TRENDING_BULLISH,
        confidence=0.8,
        is_tradeable=True,
        features={"atr": 1.0},
    )
    context.ingestion_result = {
        "rates_by_timeframe": {
            "M5": _rows(60),
            "M15": _fvg_rows(),
        }
    }

    config = TechnicalAnalysisConfig(min_candles_required=5)
    result = TechnicalAnalysisEngine(config=config).run(context)

    assert result.technical_analysis is not None
    assert result.technical_analysis.timeframe == "M5"
    confirmation_results = result.technical_analysis.metadata.get("confirmation_results") or []
    assert any(item.get("timeframe") == "M15" for item in confirmation_results)
