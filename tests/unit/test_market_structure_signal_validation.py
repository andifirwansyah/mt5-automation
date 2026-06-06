from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from src.domain.enums import MarketRegimeType, SignalDirection, ValidationStatus
from src.domain.models.regime_result import RegimeResult
from src.domain.models.signal import SignalContract
from src.engines.signal_validator import SignalValidator
from src.pipeline.rejection_reason import BUY_TOO_CLOSE_TO_RESISTANCE, MARKET_STRUCTURE_MISSING, MARKET_STRUCTURE_UNRELIABLE, SELL_TOO_CLOSE_TO_SUPPORT
from src.pipeline.trading_context import TradingContext
from src.pipeline.trading_pipeline import PIPELINE_STEP_ORDER
from src.trading.market_structure.config import MarketStructureConfig
from src.trading.market_structure.engine import MarketStructureEngine
from src.trading.market_structure.models import MarketStructureResult


class DummySession:
    def commit(self) -> None:
        return None


class SignalRepo:
    def __init__(self) -> None:
        self.session = DummySession()
        self.validations: list[dict] = []

    @staticmethod
    def count_signals_by_candle(**_kwargs):
        return 0

    def create_signal_validation(self, **kwargs):
        self.validations.append(kwargs)
        return None


class PositionRepo:
    @staticmethod
    def get_open_positions(**_kwargs):
        return []


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
            "tick_volume": 10,
            "spread": 5,
        }
    )


def _attach_signal(context: TradingContext, direction: SignalDirection, entry: float, sl: float, tp: float) -> None:
    context.ingestion_result = {"symbol_id": uuid.uuid4(), "timeframe_ids": {"M5": uuid.uuid4()}}
    context.regime_result = RegimeResult(regime=MarketRegimeType.RANGING, confidence=0.8, is_tradeable=True)
    context.signal_contract = SignalContract(
        symbol="XAUUSD",
        timeframe="M5",
        direction=direction,
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        lot_size=0.1,
        confidence=0.7,
        generated_at=context.candle_time,
        strategy_code="RANGE_REVERSION",
        metadata={"signal_id": str(uuid.uuid4())},
    )


def _structure(**overrides) -> MarketStructureResult:
    base = dict(
        symbol="XAUUSD",
        timeframe="M5",
        trend_structure="RANGING",
        current_price=2300.0,
        atr=1.0,
        nearest_support=2295.0,
        nearest_resistance=2301.0,
        distance_to_support_points=5.0,
        distance_to_resistance_points=1.0,
        is_near_support=False,
        is_near_resistance=True,
        valid_buy_zone=False,
        valid_sell_zone=True,
    )
    base.update(overrides)
    return MarketStructureResult(**base)


def _swing_rows() -> list[dict]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    closes = [100, 101, 102, 101, 100, 99, 100, 101, 103, 102, 101, 100, 99, 100, 101, 102, 101, 100, 99, 100, 101, 102, 103, 102, 101, 100, 99, 100, 101, 102, 101, 100]
    rows: list[dict] = []
    for idx, close in enumerate(closes):
        rows.append(
            {
                "time": now - timedelta(minutes=(len(closes) - idx) * 5),
                "open": float(close) - 0.2,
                "high": float(close) + 0.6,
                "low": float(close) - 0.6,
                "close": float(close),
                "tick_volume": 100 + idx,
            }
        )
    return rows


def test_pipeline_order_places_market_structure_between_technical_and_selector() -> None:
    assert PIPELINE_STEP_ORDER.index("TechnicalAnalysisEngine") < PIPELINE_STEP_ORDER.index("MarketStructureEngine")
    assert PIPELINE_STEP_ORDER.index("MarketStructureEngine") < PIPELINE_STEP_ORDER.index("StrategySelector")


def test_market_structure_engine_sets_support_resistance_context() -> None:
    context = _context()
    context.ingestion_result = {"rates_by_timeframe": {"M5": _swing_rows()}}
    context.regime_result = RegimeResult(regime=MarketRegimeType.RANGING, confidence=0.8, is_tradeable=True, features={"atr": 1.0})

    result = MarketStructureEngine(config=MarketStructureConfig(min_candles_required=20, swing_left_bars=1, swing_right_bars=1)).run(context)

    assert result.rejected is False
    assert result.market_structure is not None
    assert result.market_structure.nearest_support is not None or result.market_structure.nearest_resistance is not None
    assert result.market_structure.trend_structure in ("BULLISH", "BEARISH", "RANGING", "UNCLEAR")


def test_market_structure_config_can_be_built_from_runtime_settings() -> None:
    settings = type(
        "RuntimeSettings",
        (),
        {
            "market_structure_min_candles_required": 40,
            "market_structure_zone_tolerance_atr": 0.35,
            "market_structure_danger_zone_atr": 0.45,
            "market_structure_soft_min_room_atr": 0.70,
        },
    )()

    config = MarketStructureConfig.from_settings(settings)

    assert config.min_candles_required == 40
    assert config.zone_tolerance_atr == 0.35
    assert config.danger_zone_atr == 0.45
    assert config.minimum_room_to_zone_atr == 0.70


def test_market_structure_engine_reads_runtime_settings_per_run() -> None:
    settings = type(
        "RuntimeSettings",
        (),
        {
            "market_structure_min_candles_required": 40,
            "market_structure_zone_tolerance_atr": 0.35,
            "market_structure_danger_zone_atr": 0.45,
            "market_structure_soft_min_room_atr": 0.70,
        },
    )()
    context = _context()
    context.ingestion_result = {"rates_by_timeframe": {"M5": _swing_rows()}}

    result = MarketStructureEngine(settings=settings).run(context)

    assert result.market_structure is not None
    assert result.market_structure.metadata["reason"] == "MARKET_STRUCTURE_DATA_INSUFFICIENT"
    assert result.market_structure.metadata["candles_count"] == len(_swing_rows())


def test_signal_validator_rejects_buy_near_resistance() -> None:
    context = _context()
    _attach_signal(context, SignalDirection.BUY, entry=2300.5, sl=2298.0, tp=2303.0)
    context.market_structure = _structure(current_price=2300.5, nearest_resistance=2301.0, distance_to_resistance_points=0.5)

    out = SignalValidator(signal_repository=SignalRepo(), position_repository=PositionRepo()).run(context)

    assert out.rejected is True
    assert out.signal_validation is not None
    checks = [issue["check"] for issue in out.signal_validation.details["issues"]]
    assert BUY_TOO_CLOSE_TO_RESISTANCE in checks


def test_signal_validator_rejects_when_market_structure_missing() -> None:
    context = _context()
    _attach_signal(context, SignalDirection.BUY, entry=2295.5, sl=2293.0, tp=2300.0)

    out = SignalValidator(signal_repository=SignalRepo(), position_repository=PositionRepo()).run(context)

    assert out.rejected is True
    checks = [issue["check"] for issue in out.signal_validation.details["issues"]]
    assert MARKET_STRUCTURE_MISSING in checks


def test_signal_validator_rejects_unreliable_market_structure_even_high_confidence() -> None:
    context = _context()
    _attach_signal(context, SignalDirection.BUY, entry=2300.0, sl=2298.0, tp=2304.0)
    context.signal_contract.confidence = 0.85
    context.market_structure = MarketStructureResult(
        symbol="XAUUSD",
        timeframe="M5",
        trend_structure="UNCLEAR",
        current_price=2300.0,
        atr=1.0,
        valid_buy_zone=False,
        valid_sell_zone=False,
        metadata={"mode": "safe_unclear", "reason": "MARKET_STRUCTURE_DATA_INSUFFICIENT"},
    )

    out = SignalValidator(signal_repository=SignalRepo(), position_repository=PositionRepo()).run(context)

    assert out.rejected is True
    checks = [issue["check"] for issue in out.signal_validation.details["issues"]]
    assert MARKET_STRUCTURE_UNRELIABLE in checks


def test_signal_validator_rejects_buy_with_inverted_sl_tp() -> None:
    context = _context()
    _attach_signal(context, SignalDirection.BUY, entry=2300.0, sl=2302.0, tp=2305.0)
    context.market_structure = _structure(
        current_price=2300.0,
        nearest_support=2295.0,
        nearest_resistance=2310.0,
        is_near_support=True,
        is_near_resistance=False,
        valid_buy_zone=True,
        valid_sell_zone=False,
    )

    out = SignalValidator(signal_repository=SignalRepo(), position_repository=PositionRepo()).run(context)

    assert out.rejected is True
    checks = [issue["check"] for issue in out.signal_validation.details["issues"]]
    assert "SL_TP_DIRECTION_VALID" in checks


def test_signal_validator_rejects_sell_with_inverted_sl_tp() -> None:
    context = _context()
    _attach_signal(context, SignalDirection.SELL, entry=2300.0, sl=2298.0, tp=2295.0)
    context.market_structure = _structure(
        current_price=2300.0,
        nearest_support=2290.0,
        nearest_resistance=2305.0,
        is_near_support=False,
        is_near_resistance=True,
        valid_buy_zone=False,
        valid_sell_zone=True,
    )

    out = SignalValidator(signal_repository=SignalRepo(), position_repository=PositionRepo()).run(context)

    assert out.rejected is True
    checks = [issue["check"] for issue in out.signal_validation.details["issues"]]
    assert "SL_TP_DIRECTION_VALID" in checks


def test_signal_validator_rejects_sell_near_support() -> None:
    context = _context()
    _attach_signal(context, SignalDirection.SELL, entry=2295.5, sl=2298.0, tp=2292.0)
    context.market_structure = _structure(
        current_price=2295.5,
        nearest_support=2295.0,
        nearest_resistance=2302.0,
        distance_to_support_points=0.5,
        distance_to_resistance_points=6.5,
        is_near_support=True,
        is_near_resistance=False,
        valid_buy_zone=True,
        valid_sell_zone=False,
    )

    out = SignalValidator(signal_repository=SignalRepo(), position_repository=PositionRepo()).run(context)

    assert out.rejected is True
    checks = [issue["check"] for issue in out.signal_validation.details["issues"]]
    assert SELL_TOO_CLOSE_TO_SUPPORT in checks


def test_signal_validator_passes_buy_near_support_with_room_to_resistance() -> None:
    context = _context()
    _attach_signal(context, SignalDirection.BUY, entry=2295.5, sl=2293.0, tp=2300.0)
    context.market_structure = _structure(
        current_price=2295.5,
        nearest_support=2295.0,
        nearest_resistance=2305.0,
        distance_to_support_points=0.5,
        distance_to_resistance_points=9.5,
        is_near_support=True,
        is_near_resistance=False,
        valid_buy_zone=True,
        valid_sell_zone=False,
    )

    out = SignalValidator(signal_repository=SignalRepo(), position_repository=PositionRepo()).run(context)

    assert out.rejected is False
    assert out.signal_validation is not None
    assert out.signal_validation.status == ValidationStatus.PASSED


def test_signal_validator_uses_entry_price_not_current_price_for_structure_check() -> None:
    context = _context()
    _attach_signal(context, SignalDirection.BUY, entry=2300.5, sl=2298.0, tp=2303.0)
    context.market_structure = _structure(
        current_price=2295.5,
        nearest_support=2295.0,
        nearest_resistance=2301.0,
        distance_to_support_points=0.5,
        distance_to_resistance_points=5.5,
        is_near_support=True,
        is_near_resistance=False,
        valid_buy_zone=True,
        valid_sell_zone=False,
    )

    out = SignalValidator(signal_repository=SignalRepo(), position_repository=PositionRepo()).run(context)

    assert out.rejected is True
    checks = [issue["check"] for issue in out.signal_validation.details["issues"]]
    assert BUY_TOO_CLOSE_TO_RESISTANCE in checks


def test_signal_validator_allows_high_confidence_signal_with_soft_structure_warning() -> None:
    context = _context()
    _attach_signal(context, SignalDirection.BUY, entry=2298.0, sl=2295.0, tp=2305.0)
    context.signal_contract.confidence = 0.72
    context.market_structure = _structure(
        current_price=2298.0,
        nearest_support=2295.0,
        nearest_resistance=2305.0,
        distance_to_support_points=3.0,
        distance_to_resistance_points=7.0,
        is_near_support=False,
        is_near_resistance=False,
        valid_buy_zone=False,
        valid_sell_zone=False,
    )

    out = SignalValidator(signal_repository=SignalRepo(), position_repository=PositionRepo()).run(context)

    assert out.rejected is False
    assert out.signal_validation is not None
    assert out.signal_validation.status == ValidationStatus.PASSED
    warning_checks = [warning["check"] for warning in out.signal_validation.details["warnings"]]
    assert "BAD_MARKET_STRUCTURE_LOCATION" in warning_checks


def test_signal_validator_rejects_low_confidence_signal_with_soft_structure_issue() -> None:
    context = _context()
    _attach_signal(context, SignalDirection.BUY, entry=2298.0, sl=2295.0, tp=2305.0)
    context.signal_contract.confidence = 0.55
    context.market_structure = _structure(
        current_price=2298.0,
        nearest_support=2295.0,
        nearest_resistance=2305.0,
        distance_to_support_points=3.0,
        distance_to_resistance_points=7.0,
        is_near_support=False,
        is_near_resistance=False,
        valid_buy_zone=False,
        valid_sell_zone=False,
    )

    out = SignalValidator(signal_repository=SignalRepo(), position_repository=PositionRepo()).run(context)

    assert out.rejected is True
    checks = [issue["check"] for issue in out.signal_validation.details["issues"]]
    assert "BAD_MARKET_STRUCTURE_LOCATION" in checks
