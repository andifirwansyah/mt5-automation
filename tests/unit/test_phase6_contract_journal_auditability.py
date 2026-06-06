from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from src.domain.enums import MarketRegimeType, SignalDirection, ValidationStatus
from src.domain.models.regime_result import RegimeResult
from src.domain.models.signal import RawSignal
from src.domain.models.strategy_selection import StrategySelectionResult
from src.domain.models.validation_result import ValidationResult
from src.engines.historical_edge_validator import HistoricalEdgeValidator
from src.engines.signal_contract_builder import SignalContractBuilder
from src.engines.signal_validator import SignalValidator
from src.engines.trade_journal_engine import TradeJournalEngine
from src.pipeline.trading_context import TradingContext
from src.trading.technical_analysis.models import PatternEvidence, TechnicalAnalysisResult
from src.trading.market_structure.models import MarketStructureResult


def _context() -> TradingContext:
    return TradingContext.from_candle_event(
        {
            "symbol": "XAUUSD",
            "timeframe": "M5",
            "candle_time": datetime.now(timezone.utc).isoformat(),
            "open": 2300,
            "high": 2302,
            "low": 2299,
            "close": 2301,
        }
    )


def test_signal_contract_builder_includes_technical_summary() -> None:
    class SignalRepo:
        def __init__(self) -> None:
            self.session = type("S", (), {"commit": staticmethod(lambda: None)})()

        @staticmethod
        def create_signal(**_kwargs):
            return type("R", (), {"id": uuid.uuid4()})()

    class StrategyRepo:
        @staticmethod
        def get_active_strategies():
            return []

    ctx = _context()
    ctx.ingestion_result = {"symbol_id": str(uuid.uuid4()), "timeframe_ids": {"M5": str(uuid.uuid4())}}
    ctx.strategy_selection = StrategySelectionResult(
        strategy_code="RANGE_REVERSION",
        strategy_name="Range",
        score=0.7,
        reason="test",
        config={"lot_size": 0.01},
        details={"strategy_id": str(uuid.uuid4())},
    )
    ctx.raw_signal = RawSignal(
        direction=SignalDirection.SELL,
        confidence=0.6,
        entry_price=2301,
        stop_loss=2303,
        take_profit=2298,
        generated_at=ctx.candle_time,
        features={},
        metadata={},
    )
    ctx.technical_analysis = TechnicalAnalysisResult(
        symbol="XAUUSD",
        timeframe="M5",
        bias="sell",
        technical_score=0.66,
        buy_score=0.1,
        sell_score=0.7,
        pattern_evidence=[PatternEvidence(pattern_type="DOUBLE_TOP", signal="sell", confidence=0.8, details={"status": "neckline_broken"})],
        warnings=["warn"],
        strategy_hints=[],
        conflict_flags=[],
        metadata={},
    )

    out = SignalContractBuilder(signal_repository=SignalRepo(), strategy_repository=StrategyRepo()).run(ctx)
    summary = out.signal_contract.metadata.get("technical_summary")
    assert isinstance(summary, dict)
    assert summary.get("technical_bias") == "sell"
    assert summary.get("setup_signature")


def test_signal_validator_soft_conflict_adds_warning_not_reject() -> None:
    class SigRepo:
        def __init__(self) -> None:
            self.session = type("S", (), {"commit": staticmethod(lambda: None)})()

        @staticmethod
        def count_signals_by_candle(**_kwargs):
            return 0

        @staticmethod
        def create_signal_validation(**_kwargs):
            return None

    class PosRepo:
        @staticmethod
        def get_open_positions(**_kwargs):
            return []

    settings = type("T", (), {"max_spread": 9999, "max_open_positions_per_symbol": 99})()
    ctx = _context()
    ctx.ingestion_result = {"symbol_id": str(uuid.uuid4()), "timeframe_ids": {"M5": str(uuid.uuid4())}}
    ctx.regime_result = RegimeResult(regime=MarketRegimeType.TRENDING_BULLISH, confidence=0.7, is_tradeable=True, features={})
    ctx.strategy_selection = StrategySelectionResult(
        strategy_code="EMA_ATR_TREND",
        strategy_name="trend",
        score=0.7,
        config={},
        details={"strategy_id": str(uuid.uuid4())},
    )
    ctx.signal_contract = type(
        "C",
        (),
        {
            "direction": SignalDirection.BUY,
            "entry_price": 2300.0,
            "stop_loss": 2298.0,
            "take_profit": 2304.0,
            "confidence": 0.7,
            "generated_at": ctx.candle_time,
            "strategy_code": "EMA_ATR_TREND",
            "metadata": {
                "signal_id": str(uuid.uuid4()),
                "technical_summary": {
                    "technical_bias": "sell",
                    "buy_score": 0.1,
                    "sell_score": 0.7,
                    "setup_signature": "EMA_ATR_TREND:double_top:XAUUSD:M5",
                },
            },
        },
    )()
    ctx.market_structure = MarketStructureResult(
        symbol="XAUUSD",
        timeframe="M5",
        trend_structure="BULLISH",
        current_price=2300.0,
        atr=1.0,
        nearest_support=2295.0,
        nearest_resistance=2305.0,
        distance_to_support_points=5.0,
        distance_to_resistance_points=5.0,
        is_near_support=False,
        is_near_resistance=False,
        valid_buy_zone=True,
        valid_sell_zone=False,
    )

    out = SignalValidator(signal_repository=SigRepo(), position_repository=PosRepo(), settings=settings).run(ctx)
    assert out.rejected is False
    assert out.signal_validation is not None
    assert out.signal_validation.status == ValidationStatus.PASSED
    assert len(out.signal_validation.details.get("warnings", [])) >= 1


def test_historical_edge_reads_setup_signature_and_low_sample_warning() -> None:
    class ExecResult:
        def __init__(self, rows: list | None = None, perf=None) -> None:
            self._rows = rows or []
            self._perf = perf

        def all(self):
            return self._rows

        def scalar_one_or_none(self):
            return self._perf

    class FakeSession:
        def __init__(self) -> None:
            self.calls = 0

        def execute(self, _stmt):
            self.calls += 1
            if self.calls == 1:
                return ExecResult(rows=[])
            return ExecResult(perf=None)

        @staticmethod
        def commit() -> None:
            return None

    class SigRepo:
        def __init__(self) -> None:
            self.session = FakeSession()

        @staticmethod
        def create_historical_edge_validation(**_kwargs):
            return None

    @dataclass
    class Settings:
        min_edge_sample_size: int = 30
        allow_low_sample_edge: bool = True
        edge_min_win_rate: float = 0.45
        edge_min_profit_factor: float = 1.1

    ctx = _context()
    ctx.ingestion_result = {"symbol_id": str(uuid.uuid4()), "timeframe_ids": {"M5": str(uuid.uuid4())}}
    ctx.strategy_selection = StrategySelectionResult(
        strategy_code="EMA_ATR_TREND",
        strategy_name="trend",
        score=0.7,
        config={"historical_edge": {}},
        details={"strategy_id": str(uuid.uuid4())},
    )
    ctx.signal_contract = type("C", (), {"metadata": {"signal_id": str(uuid.uuid4()), "technical_summary": {"setup_signature": "EMA_ATR_TREND:bullish_fvg:XAUUSD:M5"}}})()

    out = HistoricalEdgeValidator(signal_repository=SigRepo(), settings=Settings()).run(ctx)
    assert out.rejected is False
    assert out.historical_edge is not None
    assert out.historical_edge.details.get("setup_signature")
    assert "LOW_SAMPLE_SIZE" in out.historical_edge.details.get("warnings", [])


def test_trade_journal_stores_ta_summary_and_blockers() -> None:
    class JournalRepo:
        def __init__(self) -> None:
            self.entries: list[dict] = []
            self.session = type("S", (), {"commit": staticmethod(lambda: None)})()

        def create_trade_journal(self, **kwargs):
            self.entries.append(kwargs)
            return None

    ctx = _context()
    ctx.reject("SIGNAL_VALIDATION_FAILED", {"message": "conflict"})
    ctx.technical_analysis = TechnicalAnalysisResult(
        symbol="XAUUSD",
        timeframe="M5",
        bias="neutral",
        technical_score=0.5,
        buy_score=0.4,
        sell_score=0.4,
        pattern_evidence=[],
        warnings=["w1"],
        strategy_hints=[],
        conflict_flags=[],
        metadata={},
    )
    ctx.signal_validation = ValidationResult(status=ValidationStatus.REJECTED, reason="SIGNAL_VALIDATION_FAILED", details={})

    repo = JournalRepo()
    TradeJournalEngine(journal_repository=repo).run(ctx)
    assert len(repo.entries) >= 1
    details = repo.entries[0]["details"]
    assert "technical_summary" in details
    assert "pipeline_blockers" in details
    assert details["rejection_reason"] == "SIGNAL_VALIDATION_FAILED"
