from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.domain.enums import MarketRegimeType, SignalDirection, ValidationStatus
from src.domain.models.regime_result import RegimeResult
from src.domain.models.signal import SignalContract
from src.engines.session_filter import SessionFilter
from src.engines.signal_quality_scorer import SignalQualityScorer
from src.engines.trade_cooldown_guard import TradeCooldownGuard
from src.pipeline.trading_context import TradingContext
from src.pipeline.trading_pipeline import PIPELINE_STEP_ORDER
from src.trading.market_structure.models import MarketStructureResult
from src.trading.technical_analysis.models import TechnicalAnalysisResult


class DummySession:
    def commit(self) -> None:
        return None


def _context(hour: int = 12) -> TradingContext:
    return TradingContext.from_candle_event(
        {
            "symbol": "XAUUSD",
            "timeframe": "M5",
            "candle_time": datetime.now(timezone.utc).replace(hour=hour, minute=0, second=0, microsecond=0).isoformat(),
            "open": 2300.0,
            "high": 2302.0,
            "low": 2299.0,
            "close": 2301.0,
            "tick_volume": 100,
            "spread": 10,
        }
    )


def _attach_signal(context: TradingContext, confidence: float = 0.75) -> None:
    context.ingestion_result = {"symbol_id": uuid.uuid4(), "timeframe_ids": {"M5": uuid.uuid4()}}
    context.regime_result = RegimeResult(regime=MarketRegimeType.TRENDING_BULLISH, confidence=0.8, is_tradeable=True, features={})
    context.signal_contract = SignalContract(
        symbol="XAUUSD",
        timeframe="M5",
        direction=SignalDirection.BUY,
        entry_price=2300.0,
        stop_loss=2298.0,
        take_profit=2304.0,
        lot_size=0.01,
        confidence=confidence,
        generated_at=context.candle_time,
        strategy_code="EMA_ATR_TREND",
        metadata={"signal_id": str(uuid.uuid4())},
    )


def test_pipeline_order_includes_professional_guards() -> None:
    assert PIPELINE_STEP_ORDER.index("MarketEventFilter") < PIPELINE_STEP_ORDER.index("SessionFilter")
    assert PIPELINE_STEP_ORDER.index("SessionFilter") < PIPELINE_STEP_ORDER.index("MarketRegimeEngine")
    assert PIPELINE_STEP_ORDER.index("SignalContractBuilder") < PIPELINE_STEP_ORDER.index("SignalQualityScorer")
    assert PIPELINE_STEP_ORDER.index("SignalQualityScorer") < PIPELINE_STEP_ORDER.index("SignalValidator")
    assert PIPELINE_STEP_ORDER.index("RiskEngine") < PIPELINE_STEP_ORDER.index("TradeCooldownGuard")
    assert PIPELINE_STEP_ORDER.index("TradeCooldownGuard") < PIPELINE_STEP_ORDER.index("PreTradeSimulation")


def test_session_filter_blocks_rollover() -> None:
    settings = type("Settings", (), {"session_filter_allowed_sessions": "ASIA,LONDON,NEW_YORK", "session_filter_block_rollover": True})()
    context = _context(hour=22)

    out = SessionFilter(settings=settings).run(context)

    assert out.rejected is True
    assert out.rejection_reason == "SESSION_ROLLOVER_BLOCKED"


def test_session_filter_allows_london_session() -> None:
    settings = type("Settings", (), {"session_filter_allowed_sessions": "ASIA,LONDON,NEW_YORK", "session_filter_block_rollover": True})()
    context = _context(hour=8)

    out = SessionFilter(settings=settings).run(context)

    assert out.rejected is False
    assert out.session_filter_result is not None
    assert out.session_filter_result.status == ValidationStatus.PASSED


def test_signal_quality_scorer_passes_good_signal() -> None:
    settings = type("Settings", (), {"signal_quality_min_score": 0.45, "min_rr": 1.3, "max_spread": 70})()
    context = _context()
    _attach_signal(context, confidence=0.78)
    context.technical_analysis = TechnicalAnalysisResult(symbol="XAUUSD", timeframe="M5", bias="buy", technical_score=0.75, buy_score=0.8)
    context.market_structure = MarketStructureResult(
        symbol="XAUUSD",
        timeframe="M5",
        trend_structure="BULLISH",
        current_price=2300.0,
        atr=1.0,
        nearest_support=2298.0,
        nearest_resistance=2308.0,
        valid_buy_zone=True,
        valid_sell_zone=False,
    )

    out = SignalQualityScorer(settings=settings).run(context)

    assert out.rejected is False
    assert out.signal_quality is not None
    assert out.signal_quality.passed is True
    assert out.signal_quality.grade in {"A", "B", "C"}


def test_signal_quality_scorer_rejects_low_quality_signal() -> None:
    settings = type("Settings", (), {"signal_quality_min_score": 0.70, "min_rr": 2.0, "max_spread": 20})()
    context = _context()
    _attach_signal(context, confidence=0.20)
    context.technical_analysis = TechnicalAnalysisResult(symbol="XAUUSD", timeframe="M5", bias="sell", technical_score=0.2, sell_score=0.8)
    context.market_structure = MarketStructureResult(
        symbol="XAUUSD",
        timeframe="M5",
        trend_structure="BEARISH",
        current_price=2300.0,
        atr=1.0,
        nearest_support=2298.0,
        nearest_resistance=2301.0,
        is_near_resistance=True,
        valid_buy_zone=False,
        valid_sell_zone=True,
    )

    out = SignalQualityScorer(settings=settings).run(context)

    assert out.rejected is True
    assert out.rejection_reason == "SIGNAL_QUALITY_FAILED"


def test_trade_cooldown_guard_rejects_recent_signal() -> None:
    class SignalRepo:
        session = DummySession()

        @staticmethod
        def count_recent_signals(**_kwargs):
            return 1

    settings = type("Settings", (), {"trade_cooldown_minutes": 10})()
    context = _context()
    _attach_signal(context)

    out = TradeCooldownGuard(signal_repository=SignalRepo(), settings=settings).run(context)

    assert out.rejected is True
    assert out.rejection_reason == "TRADE_COOLDOWN_ACTIVE"


def test_trade_cooldown_guard_passes_without_recent_signal() -> None:
    class SignalRepo:
        session = DummySession()

        @staticmethod
        def count_recent_signals(**_kwargs):
            return 0

    settings = type("Settings", (), {"trade_cooldown_minutes": 10})()
    context = _context()
    _attach_signal(context)

    out = TradeCooldownGuard(signal_repository=SignalRepo(), settings=settings).run(context)

    assert out.rejected is False
    assert out.trade_cooldown_result is not None
    assert out.trade_cooldown_result.status == ValidationStatus.PASSED
