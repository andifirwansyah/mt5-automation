"""Acceptance check for precise rejection reasons in regime/selector flow."""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.domain.enums import MarketRegimeType
from src.domain.models.regime_result import RegimeResult
from src.engines.market_regime_engine import MarketRegimeEngine
from src.engines.strategy_selector import StrategySelector
from src.pipeline.rejection_reason import CHOPPY_MARKET_NO_TRADE, LOW_VOLATILITY_NO_TRADE, NO_STRATEGY_SELECTED
from src.pipeline.trading_context import TradingContext


class FakeRegimeRepository:
    """No-op regime repository for acceptance checks."""

    def __init__(self) -> None:
        self.session = self

    def create_market_regime(self, **_kwargs):
        return None

    def commit(self) -> None:
        return None


@dataclass
class _StrategyRow:
    id: uuid.UUID
    code: str
    name: str


@dataclass
class _ConfigRow:
    config: dict


class FakeStrategyRepository:
    """Simple fake strategy repository with call counter."""

    def __init__(self, strategy_codes: list[str]) -> None:
        self._rows = [_StrategyRow(id=uuid.uuid4(), code=code, name=code) for code in strategy_codes]
        self.called_get_active = 0
        self.session = self

    def get_active_strategies(self):
        self.called_get_active += 1
        return self._rows

    def get_active_strategy_configs(self, **_kwargs):
        return [_ConfigRow(config={"allow_high_volatility": True, "lot_size": 0.01})]

    def create_strategy_selection(self, **_kwargs):
        return None

    def commit(self) -> None:
        return None


def _build_context() -> TradingContext:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return TradingContext.from_candle_event(
        {
            "symbol": "XAUUSD",
            "timeframe": "M5",
            "candle_time": now.isoformat(),
            "open": 2300.0,
            "high": 2302.0,
            "low": 2299.0,
            "close": 2301.0,
            "tick_volume": 100,
        }
    )


def _build_low_vol_rows(n: int = 80) -> list[dict]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows: list[dict] = []
    for i in range(n):
        base = 2300.0 + (i * 0.01)
        rows.append(
            {
                "time": now - timedelta(minutes=(n - i) * 5),
                "open": base,
                "high": base + 0.01,
                "low": base - 0.01,
                "close": base + 0.005,
            }
        )
    return rows


def _build_choppy_rows(n: int = 80) -> list[dict]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows: list[dict] = []
    for i in range(n):
        base = 2300.0 + ((-1) ** i) * 0.2
        rows.append(
            {
                "time": now - timedelta(minutes=(n - i) * 5),
                "open": base,
                "high": base + 1.5,
                "low": base - 1.5,
                "close": base + 0.01,
            }
        )
    return rows


def main() -> None:
    # [A] LOW_VOLATILITY reason precision from MarketRegimeEngine
    context_low = _build_context()
    context_low.ingestion_result = {"rates_by_timeframe": {"M5": _build_low_vol_rows()}}
    regime_engine_low = MarketRegimeEngine(
        regime_repository=FakeRegimeRepository(),
        high_vol_threshold=1.0,
        low_vol_threshold=0.01,
    )
    out_low = regime_engine_low.run(context_low)
    low_volatility_regime_reason_precise = (
        out_low.regime_result is not None
        and out_low.regime_result.regime == MarketRegimeType.LOW_VOLATILITY
        and out_low.regime_result.is_tradeable is False
        and out_low.regime_result.reason == LOW_VOLATILITY_NO_TRADE
    )

    # [B] CHOPPY reason precision from MarketRegimeEngine
    context_choppy = _build_context()
    context_choppy.ingestion_result = {"rates_by_timeframe": {"M5": _build_choppy_rows()}}
    regime_engine_choppy = MarketRegimeEngine(
        regime_repository=FakeRegimeRepository(),
        high_vol_threshold=1.0,
        low_vol_threshold=0.000001,
        choppy_threshold=1.0,
        trend_threshold=5.0,
    )
    out_choppy = regime_engine_choppy.run(context_choppy)
    choppy_regime_reason_precise = (
        out_choppy.regime_result is not None
        and out_choppy.regime_result.regime == MarketRegimeType.CHOPPY
        and out_choppy.regime_result.is_tradeable is False
        and out_choppy.regime_result.reason == CHOPPY_MARKET_NO_TRADE
    )

    # [C]/[D] StrategySelector explicit reject for no-trade regimes
    selector_repo_low = FakeStrategyRepository(strategy_codes=["EMA_ATR_TREND", "RANGE_REVERSION", "VOLATILITY_BREAKOUT"])
    selector_low = StrategySelector(strategy_repository=selector_repo_low)
    context_selector_low = _build_context()
    context_selector_low.regime_result = RegimeResult(
        regime=MarketRegimeType.LOW_VOLATILITY,
        confidence=0.3,
        is_tradeable=False,
        reason=LOW_VOLATILITY_NO_TRADE,
        features={"volatility_score": 0.001},
    )
    out_selector_low = selector_low.run(context_selector_low)

    selector_low_vol_reject_precise = out_selector_low.rejected and out_selector_low.rejection_reason == LOW_VOLATILITY_NO_TRADE
    selector_low_vol_no_repo_call = selector_repo_low.called_get_active == 0

    selector_repo_choppy = FakeStrategyRepository(strategy_codes=["EMA_ATR_TREND", "RANGE_REVERSION", "VOLATILITY_BREAKOUT"])
    selector_choppy = StrategySelector(strategy_repository=selector_repo_choppy)
    context_selector_choppy = _build_context()
    context_selector_choppy.regime_result = RegimeResult(
        regime=MarketRegimeType.CHOPPY,
        confidence=0.4,
        is_tradeable=False,
        reason=CHOPPY_MARKET_NO_TRADE,
        features={"trend_strength": 0.1},
    )
    out_selector_choppy = selector_choppy.run(context_selector_choppy)

    selector_choppy_reject_precise = out_selector_choppy.rejected and out_selector_choppy.rejection_reason == CHOPPY_MARKET_NO_TRADE
    selector_choppy_no_repo_call = selector_repo_choppy.called_get_active == 0

    # [E]/[F]/[G] Existing mapping still works
    selector_repo_tradeable = FakeStrategyRepository(strategy_codes=["EMA_ATR_TREND", "RANGE_REVERSION", "VOLATILITY_BREAKOUT"])
    selector_tradeable = StrategySelector(strategy_repository=selector_repo_tradeable)

    def run_select(regime: MarketRegimeType) -> TradingContext:
        c = _build_context()
        c.ingestion_result = {"symbol_id": str(uuid.uuid4()), "timeframe_ids": {"M5": str(uuid.uuid4())}}
        c.regime_result = RegimeResult(regime=regime, confidence=0.8, is_tradeable=True, features={})
        return selector_tradeable.run(c)

    bullish_ctx = run_select(MarketRegimeType.TRENDING_BULLISH)
    ranging_ctx = run_select(MarketRegimeType.RANGING)
    high_vol_ctx = run_select(MarketRegimeType.HIGH_VOLATILITY)

    selector_mapping_still_valid = (
        bullish_ctx.strategy_selection is not None
        and bullish_ctx.strategy_selection.strategy_code == "EMA_ATR_TREND"
        and ranging_ctx.strategy_selection is not None
        and ranging_ctx.strategy_selection.strategy_code == "RANGE_REVERSION"
        and high_vol_ctx.strategy_selection is not None
        and high_vol_ctx.strategy_selection.strategy_code == "VOLATILITY_BREAKOUT"
    )

    no_trade_not_using_generic = (
        out_selector_low.rejection_reason != NO_STRATEGY_SELECTED
        and out_selector_choppy.rejection_reason != NO_STRATEGY_SELECTED
    )

    details_audit_ready = (
        isinstance(out_selector_low.rejection_details, dict)
        and "regime" in out_selector_low.rejection_details
        and "confidence" in out_selector_low.rejection_details
        and "features" in out_selector_low.rejection_details
        and "regime_reason" in out_selector_low.rejection_details
    )

    print("low_volatility_regime_reason_precise", low_volatility_regime_reason_precise)
    print("choppy_regime_reason_precise", choppy_regime_reason_precise)
    print("selector_low_vol_reject_precise", selector_low_vol_reject_precise)
    print("selector_choppy_reject_precise", selector_choppy_reject_precise)
    print("selector_low_vol_no_repo_call", selector_low_vol_no_repo_call)
    print("selector_choppy_no_repo_call", selector_choppy_no_repo_call)
    print("no_trade_not_using_generic_reason", no_trade_not_using_generic)
    print("selector_reject_details_audit_ready", details_audit_ready)
    print("selector_mapping_still_valid", selector_mapping_still_valid)


if __name__ == "__main__":
    main()
