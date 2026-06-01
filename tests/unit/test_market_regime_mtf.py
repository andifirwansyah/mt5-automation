from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from src.domain.enums import MarketRegimeType
from src.domain.models.regime_result import RegimeResult
from src.engines.market_regime_engine import MarketRegimeEngine
from src.pipeline.trading_context import TradingContext


class _Session:
    @staticmethod
    def commit() -> None:
        return None


class _RegimeRepo:
    def __init__(self) -> None:
        self.session = _Session()
        self.calls: list[dict] = []

    def create_market_regime(self, **kwargs):
        self.calls.append(kwargs)
        return None


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
            "tick_volume": 100,
        }
    )


def _rows(count: int = 80) -> list[dict]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows: list[dict] = []
    for i in range(count):
        base = 2300.0 + (i * 0.01)
        rows.append(
            {
                "time": now,
                "open": base,
                "high": base + 0.2,
                "low": base - 0.2,
                "close": base + 0.05,
                "tick_volume": 100 + i,
            }
        )
    return rows


def test_market_regime_engine_fuses_with_htf_weighted_vote() -> None:
    repo = _RegimeRepo()
    engine = MarketRegimeEngine(
        regime_repository=repo,
        confirmation_timeframes=["M15", "H1"],
        primary_timeframe_weight=0.5,
    )
    context = _context()
    context.ingestion_result = {
        "rates_by_timeframe": {
            "M5": _rows(),
            "M15": _rows(),
            "H1": _rows(),
        },
    }

    primary = RegimeResult(regime=MarketRegimeType.RANGING, confidence=0.55, is_tradeable=True, features={"atr": 1.0})
    htf_1 = RegimeResult(regime=MarketRegimeType.TRENDING_BULLISH, confidence=0.9, is_tradeable=True, features={"atr": 1.1})
    htf_2 = RegimeResult(regime=MarketRegimeType.TRENDING_BULLISH, confidence=0.8, is_tradeable=True, features={"atr": 1.2})

    with patch.object(MarketRegimeEngine, "_evaluate_regime_from_dataframe", side_effect=[primary, htf_1, htf_2]):
        out = engine.run(context)

    assert out.regime_result is not None
    assert out.regime_result.regime == MarketRegimeType.TRENDING_BULLISH
    assert out.regime_result.is_tradeable is True
    assert out.regime_result.features.get("mtf_alignment_with_primary") is False
    assert "M15" in (out.regime_result.features.get("mtf_confirmation") or {})
    assert "H1" in (out.regime_result.features.get("mtf_confirmation") or {})


def test_market_regime_engine_preserves_primary_not_tradeable() -> None:
    repo = _RegimeRepo()
    engine = MarketRegimeEngine(
        regime_repository=repo,
        confirmation_timeframes=["M15"],
    )
    context = _context()
    context.ingestion_result = {
        "rates_by_timeframe": {
            "M5": _rows(),
            "M15": _rows(),
        },
    }

    primary = RegimeResult(
        regime=MarketRegimeType.CHOPPY,
        confidence=0.8,
        is_tradeable=False,
        reason="CHOPPY_MARKET_NO_TRADE",
        features={"atr": 1.0},
    )
    htf = RegimeResult(regime=MarketRegimeType.TRENDING_BULLISH, confidence=0.9, is_tradeable=True, features={"atr": 1.4})

    with patch.object(MarketRegimeEngine, "_evaluate_regime_from_dataframe", side_effect=[primary, htf]):
        out = engine.run(context)

    assert out.regime_result is not None
    assert out.regime_result.regime == MarketRegimeType.CHOPPY
    assert out.regime_result.is_tradeable is False
    assert out.regime_result.reason == "CHOPPY_MARKET_NO_TRADE"
