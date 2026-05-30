from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.domain.enums import ExecutionDecisionStatus, MarketRegimeType, OrderExecutionStatus, SignalDirection, ValidationStatus
from src.domain.models.broker_health import BrokerHealth
from src.domain.models.edge_result import EdgeResult
from src.domain.models.execution_decision import ExecutionDecision
from src.domain.models.regime_result import RegimeResult
from src.domain.models.risk_plan import RiskPlan
from src.domain.models.signal import SignalContract
from src.domain.models.simulation_result import SimulationResult
from src.domain.models.validation_result import ValidationResult
from src.engines.data_quality_guard import DataQualityGuard
from src.engines.execution_engine import ExecutionEngine
from src.engines.execution_gate import ExecutionGate
from src.engines.kill_switch_monitor import KillSwitchMonitor
from src.engines.risk_engine import RiskEngine
from src.engines.signal_validator import SignalValidator
from src.engines.market_regime_engine import MarketRegimeEngine
from src.engines.strategy_selector import StrategySelector
from src.orchestrators.trading_orchestrator import TradingOrchestrator
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.rejection_reason import (
    CHOPPY_MARKET_NO_TRADE,
    LOW_VOLATILITY_NO_TRADE,
)
from src.pipeline.trading_context import TradingContext


class DummySession:
    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def execute(self, *_args, **_kwargs):
        class _R:
            @staticmethod
            def scalar_one():
                return 0

            @staticmethod
            def all():
                return []

        return _R()


@dataclass
class _StrategyRow:
    id: uuid.UUID
    code: str
    name: str


@dataclass
class _StrategyConfigRow:
    config: dict


@dataclass
class _PerformanceRow:
    total_trades: int
    win_rate: float
    net_profit: float
    profit_factor: float
    details: dict


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


def _attach_pre_execution_passed_fields(context: TradingContext) -> None:
    context.data_quality_result = ValidationResult(status=ValidationStatus.PASSED)
    context.market_event_result = ValidationResult(status=ValidationStatus.PASSED)
    context.regime_result = RegimeResult(regime=MarketRegimeType.TRENDING_BULLISH, confidence=0.8, is_tradeable=True)
    context.signal_validation = ValidationResult(status=ValidationStatus.PASSED)
    context.historical_edge = EdgeResult(passed=True, sample_size=1, win_rate=1.0, expectancy=1.0)
    context.risk_plan = RiskPlan(
        passed=True,
        lot_size=0.1,
        entry_price=2301.0,
        stop_loss=2299.0,
        take_profit=2305.0,
        risk_per_trade_pct=1.0,
        max_daily_loss_pct=5.0,
    )
    context.simulation_result = SimulationResult(passed=True, expected_profit=1.0, expected_drawdown=1.0, slippage_estimate=0.1)


def test_trading_context_reject_behavior() -> None:
    context = _context()
    context.reject("RISK_FAILED", {"message": "invalid"})
    assert context.rejected is True
    assert context.rejection_reason == "RISK_FAILED"
    assert context.rejection_details == {"message": "invalid"}


def test_reject_without_reason_is_invalid() -> None:
    context = _context()
    try:
        context.reject("", {"x": 1})
        assert False, "Expected ValueError for empty rejection reason"
    except ValueError:
        assert True


def test_pipeline_stops_when_context_rejected() -> None:
    class RejectStep(PipelineStep):
        @property
        def name(self) -> str:
            return "RejectStep"

        def run(self, context: TradingContext) -> TradingContext:
            context.reject("STOP_HERE", {"x": 1})
            return context

    class CounterStep(PipelineStep):
        called = 0

        @property
        def name(self) -> str:
            return "CounterStep"

        def run(self, context: TradingContext) -> TradingContext:
            CounterStep.called += 1
            return context

    class AuditRunner:
        def run_and_audit(self, step: PipelineStep, context: TradingContext) -> TradingContext:
            return step.run(context)

    step2 = CounterStep()
    orchestrator = TradingOrchestrator([RejectStep(), step2], engine_audit_service=AuditRunner())
    result = orchestrator.run_cycle({"symbol": "XAUUSD", "timeframe": "M5", "open": 1, "high": 2, "low": 0.5, "close": 1.5})
    assert result.rejected is True
    assert CounterStep.called == 0


def test_data_quality_guard_rejects_invalid_ohlc() -> None:
    class MarketRepo:
        def __init__(self) -> None:
            self.session = DummySession()

        def create_data_quality_check(self, **_kwargs):
            return None

    class CandleSvc:
        @staticmethod
        def get_latest_candles(**_kwargs):
            return []

    context = _context()
    context.market_snapshot.high_price = 100.0
    context.market_snapshot.low_price = 110.0

    engine = DataQualityGuard(market_repository=MarketRepo(), candle_service=CandleSvc())
    result = engine.run(context)
    assert result.rejected is True
    assert result.rejection_reason == "DATA_QUALITY_FAILED"


def test_strategy_selector_rejects_choppy() -> None:
    class StrategyRepo:
        def __init__(self) -> None:
            self.called = 0

        def get_active_strategies(self):
            self.called += 1
            return []

    context = _context()
    context.regime_result = RegimeResult(
        regime=MarketRegimeType.CHOPPY,
        confidence=0.9,
        is_tradeable=False,
        reason=CHOPPY_MARKET_NO_TRADE,
        features={"trend_strength": 0.1},
    )
    repo = StrategyRepo()
    engine = StrategySelector(strategy_repository=repo)
    result = engine.run(context)
    assert result.rejected is True
    assert result.rejection_reason == CHOPPY_MARKET_NO_TRADE
    assert repo.called == 0


def test_market_regime_engine_low_volatility_sets_no_trade_reason() -> None:
    class RegimeRepo:
        def __init__(self) -> None:
            self.session = DummySession()

        @staticmethod
        def create_market_regime(**_kwargs):
            return None

    context = _context()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows = []
    for i in range(70):
        base = 2300.0 + (i * 0.01)
        rows.append({"time": now, "open": base, "high": base + 0.01, "low": base - 0.01, "close": base + 0.005})
    context.ingestion_result = {"rates_by_timeframe": {"M5": rows}}

    engine = MarketRegimeEngine(
        regime_repository=RegimeRepo(),
        high_vol_threshold=1.0,
        low_vol_threshold=0.01,
    )
    result = engine.run(context)
    assert result.regime_result is not None
    assert result.regime_result.regime == MarketRegimeType.LOW_VOLATILITY
    assert result.regime_result.is_tradeable is False
    assert result.regime_result.reason == LOW_VOLATILITY_NO_TRADE


def test_market_regime_engine_choppy_sets_no_trade_reason() -> None:
    class RegimeRepo:
        def __init__(self) -> None:
            self.session = DummySession()

        @staticmethod
        def create_market_regime(**_kwargs):
            return None

    context = _context()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows = []
    for i in range(70):
        base = 2300.0 + ((-1) ** i) * 0.1
        rows.append({"time": now, "open": base, "high": base + 2.0, "low": base - 2.0, "close": base + 0.01})
    context.ingestion_result = {"rates_by_timeframe": {"M5": rows}}

    engine = MarketRegimeEngine(
        regime_repository=RegimeRepo(),
        high_vol_threshold=1.0,
        low_vol_threshold=0.000001,
        choppy_threshold=1.0,
        trend_threshold=5.0,
    )
    result = engine.run(context)
    assert result.regime_result is not None
    assert result.regime_result.regime == MarketRegimeType.CHOPPY
    assert result.regime_result.is_tradeable is False
    assert result.regime_result.reason == CHOPPY_MARKET_NO_TRADE


def test_strategy_selector_rejects_low_volatility_explicitly() -> None:
    class StrategyRepo:
        def __init__(self) -> None:
            self.called = 0

        def get_active_strategies(self):
            self.called += 1
            return []

    context = _context()
    context.regime_result = RegimeResult(
        regime=MarketRegimeType.LOW_VOLATILITY,
        confidence=0.3,
        is_tradeable=False,
        reason=LOW_VOLATILITY_NO_TRADE,
        features={"volatility_score": 0.001},
    )
    repo = StrategyRepo()
    result = StrategySelector(strategy_repository=repo).run(context)
    assert result.rejected is True
    assert result.rejection_reason == LOW_VOLATILITY_NO_TRADE
    assert repo.called == 0


def test_strategy_selector_selects_ema_atr_for_trending_bullish() -> None:
    class StrategyRepo:
        def __init__(self) -> None:
            self.session = DummySession()
            self._rows = [
                _StrategyRow(id=uuid.uuid4(), code="EMA_ATR_TREND", name="EMA ATR"),
                _StrategyRow(id=uuid.uuid4(), code="RANGE_REVERSION", name="RANGE"),
            ]

        def get_active_strategies(self):
            return self._rows

        def get_active_strategy_configs(self, **_kwargs):
            return [_StrategyConfigRow(config={"lot_size": 0.01})]

        @staticmethod
        def create_strategy_selection(**_kwargs):
            return None

    context = _context()
    context.ingestion_result = {"symbol_id": str(uuid.uuid4()), "timeframe_ids": {"M5": str(uuid.uuid4())}}
    context.regime_result = RegimeResult(
        regime=MarketRegimeType.TRENDING_BULLISH,
        confidence=0.75,
        is_tradeable=True,
        features={"trend_strength": 1.2},
    )
    result = StrategySelector(strategy_repository=StrategyRepo()).run(context)
    assert result.rejected is False
    assert result.strategy_selection is not None
    assert result.strategy_selection.strategy_code == "EMA_ATR_TREND"


def test_strategy_selector_selects_range_reversion_for_ranging() -> None:
    class StrategyRepo:
        def __init__(self) -> None:
            self.session = DummySession()
            self._rows = [
                _StrategyRow(id=uuid.uuid4(), code="EMA_ATR_TREND", name="EMA ATR"),
                _StrategyRow(id=uuid.uuid4(), code="RANGE_REVERSION", name="RANGE"),
            ]

        def get_active_strategies(self):
            return self._rows

        def get_active_strategy_configs(self, **_kwargs):
            return [_StrategyConfigRow(config={"lot_size": 0.01})]

        @staticmethod
        def create_strategy_selection(**_kwargs):
            return None

    context = _context()
    context.ingestion_result = {"symbol_id": str(uuid.uuid4()), "timeframe_ids": {"M5": str(uuid.uuid4())}}
    context.regime_result = RegimeResult(regime=MarketRegimeType.RANGING, confidence=0.8, is_tradeable=True, features={})
    result = StrategySelector(strategy_repository=StrategyRepo()).run(context)
    assert result.rejected is False
    assert result.strategy_selection is not None
    assert result.strategy_selection.strategy_code == "RANGE_REVERSION"


def test_strategy_selector_selects_volatility_breakout_for_high_volatility() -> None:
    class StrategyRepo:
        def __init__(self) -> None:
            self.session = DummySession()
            self._rows = [
                _StrategyRow(id=uuid.uuid4(), code="EMA_ATR_TREND", name="EMA ATR"),
                _StrategyRow(id=uuid.uuid4(), code="LIQUIDITY_SWEEP_REVERSAL", name="LIQUIDITY"),
                _StrategyRow(id=uuid.uuid4(), code="VOLATILITY_BREAKOUT", name="BREAKOUT"),
            ]

        def get_active_strategies(self):
            return self._rows

        def get_active_strategy_configs(self, **_kwargs):
            return [_StrategyConfigRow(config={"allow_high_volatility": True, "lot_size": 0.01})]

        @staticmethod
        def create_strategy_selection(**_kwargs):
            return None

    context = _context()
    context.ingestion_result = {"symbol_id": str(uuid.uuid4()), "timeframe_ids": {"M5": str(uuid.uuid4())}}
    context.regime_result = RegimeResult(
        regime=MarketRegimeType.HIGH_VOLATILITY,
        confidence=0.85,
        is_tradeable=True,
        features={"volatility_score": 0.04},
    )
    result = StrategySelector(strategy_repository=StrategyRepo()).run(context)
    assert result.rejected is False
    assert result.strategy_selection is not None
    assert result.strategy_selection.strategy_code == "VOLATILITY_BREAKOUT"


def test_strategy_selector_high_volatility_fallback_to_liquidity_when_breakout_config_blocks() -> None:
    class StrategyRepo:
        def __init__(self) -> None:
            self.session = DummySession()
            self.breakout_id = uuid.uuid4()
            self.liquidity_id = uuid.uuid4()
            self._rows = [
                _StrategyRow(id=self.breakout_id, code="VOLATILITY_BREAKOUT", name="BREAKOUT"),
                _StrategyRow(id=self.liquidity_id, code="LIQUIDITY_SWEEP_REVERSAL", name="LIQUIDITY"),
            ]

        def get_active_strategies(self):
            return self._rows

        def get_active_strategy_configs(self, strategy_id, **_kwargs):
            if strategy_id == self.breakout_id:
                return [_StrategyConfigRow(config={"allow_high_volatility": False})]
            return [_StrategyConfigRow(config={"allow_high_volatility": True})]

        @staticmethod
        def create_strategy_selection(**_kwargs):
            return None

    context = _context()
    context.ingestion_result = {"symbol_id": str(uuid.uuid4()), "timeframe_ids": {"M5": str(uuid.uuid4())}}
    context.regime_result = RegimeResult(
        regime=MarketRegimeType.HIGH_VOLATILITY,
        confidence=0.9,
        is_tradeable=True,
        features={"volatility_score": 0.05},
    )
    result = StrategySelector(strategy_repository=StrategyRepo()).run(context)
    assert result.rejected is False
    assert result.strategy_selection is not None
    assert result.strategy_selection.strategy_code == "LIQUIDITY_SWEEP_REVERSAL"


def test_strategy_selector_weighted_performance_overrides_default_high_volatility_priority() -> None:
    class StrategyRepo:
        def __init__(self) -> None:
            self.session = DummySession()
            self.breakout_id = uuid.uuid4()
            self.liquidity_id = uuid.uuid4()
            self._rows = [
                _StrategyRow(id=self.breakout_id, code="VOLATILITY_BREAKOUT", name="BREAKOUT"),
                _StrategyRow(id=self.liquidity_id, code="LIQUIDITY_SWEEP_REVERSAL", name="LIQUIDITY"),
            ]
            self._performance = {
                self.breakout_id: [
                    _PerformanceRow(
                        total_trades=20,
                        win_rate=0.40,
                        net_profit=-100.0,
                        profit_factor=0.7,
                        details={},
                    )
                ],
                self.liquidity_id: [
                    _PerformanceRow(
                        total_trades=20,
                        win_rate=0.55,
                        net_profit=80.0,
                        profit_factor=1.8,
                        details={},
                    )
                ],
            }

        def get_active_strategies(self):
            return self._rows

        def get_active_strategy_configs(self, **_kwargs):
            return [_StrategyConfigRow(config={"allow_high_volatility": True, "lot_size": 0.01})]

        def get_recent_performance_by_strategy(self, strategy_id, limit=30):
            return self._performance.get(strategy_id, [])[:limit]

        @staticmethod
        def create_strategy_selection(**_kwargs):
            return None

    context = _context()
    context.ingestion_result = {"symbol_id": str(uuid.uuid4()), "timeframe_ids": {"M5": str(uuid.uuid4())}}
    context.regime_result = RegimeResult(
        regime=MarketRegimeType.HIGH_VOLATILITY,
        confidence=0.88,
        is_tradeable=True,
        features={"volatility_score": 0.05},
    )
    result = StrategySelector(strategy_repository=StrategyRepo()).run(context)
    assert result.rejected is False
    assert result.strategy_selection is not None
    assert result.strategy_selection.strategy_code == "LIQUIDITY_SWEEP_REVERSAL"
    assert result.strategy_selection.details.get("selector_mode") == "weighted_performance"


def test_strategy_selector_falls_back_when_weighted_performance_sample_is_too_low() -> None:
    class StrategyRepo:
        def __init__(self) -> None:
            self.session = DummySession()
            self.ema_id = uuid.uuid4()
            self.range_id = uuid.uuid4()
            self._rows = [
                _StrategyRow(id=self.ema_id, code="EMA_ATR_TREND", name="EMA ATR"),
                _StrategyRow(id=self.range_id, code="TREND_ALT", name="TREND ALT"),
            ]
            self._performance = {
                self.ema_id: [
                    _PerformanceRow(
                        total_trades=1,
                        win_rate=1.0,
                        net_profit=10.0,
                        profit_factor=2.0,
                        details={},
                    )
                ],
                self.range_id: [
                    _PerformanceRow(
                        total_trades=1,
                        win_rate=0.0,
                        net_profit=-10.0,
                        profit_factor=0.2,
                        details={},
                    )
                ],
            }

        def get_active_strategies(self):
            return self._rows

        def get_active_strategy_configs(self, **_kwargs):
            return [_StrategyConfigRow(config={"lot_size": 0.01})]

        def get_recent_performance_by_strategy(self, strategy_id, limit=30):
            return self._performance.get(strategy_id, [])[:limit]

        @staticmethod
        def create_strategy_selection(**_kwargs):
            return None

    context = _context()
    context.ingestion_result = {"symbol_id": str(uuid.uuid4()), "timeframe_ids": {"M5": str(uuid.uuid4())}}
    context.regime_result = RegimeResult(
        regime=MarketRegimeType.TRENDING_BULLISH,
        confidence=0.80,
        is_tradeable=True,
        features={"trend_strength": 1.2},
    )
    result = StrategySelector(strategy_repository=StrategyRepo()).run(context)
    assert result.rejected is False
    assert result.strategy_selection is not None
    assert result.strategy_selection.strategy_code == "EMA_ATR_TREND"
    assert result.strategy_selection.details.get("selector_mode") == "fallback_token_order"


def test_signal_validator_rejects_duplicate_signal() -> None:
    class SignalRepo:
        def __init__(self) -> None:
            self.session = DummySession()

        @staticmethod
        def count_signals_by_candle(**_kwargs):
            return 1

        @staticmethod
        def create_signal_validation(**_kwargs):
            return None

    class PositionRepo:
        @staticmethod
        def get_open_positions(**_kwargs):
            return []

    context = _context()
    signal_id = uuid.uuid4()
    symbol_id = uuid.uuid4()
    timeframe_id = uuid.uuid4()
    context.ingestion_result = {"symbol_id": symbol_id, "timeframe_ids": {"M5": timeframe_id}}
    context.signal_contract = SignalContract(
        symbol="XAUUSD",
        timeframe="M5",
        direction=SignalDirection.BUY,
        entry_price=2300.0,
        stop_loss=2299.0,
        take_profit=2303.0,
        lot_size=0.1,
        confidence=0.7,
        generated_at=context.candle_time,
        strategy_code="EMA_ATR_TREND",
        metadata={"signal_id": str(signal_id)},
    )
    context.regime_result = RegimeResult(regime=MarketRegimeType.TRENDING_BULLISH, confidence=0.8, is_tradeable=True)

    engine = SignalValidator(signal_repository=SignalRepo(), position_repository=PositionRepo())
    result = engine.run(context)
    assert result.rejected is True
    assert result.rejection_reason == "SIGNAL_VALIDATION_FAILED"


def test_risk_engine_requires_sl_and_tp() -> None:
    class RiskRepo:
        def __init__(self) -> None:
            self.session = DummySession()

        @staticmethod
        def create_risk_assessment(**_kwargs):
            return None

    context = _context()
    context.signal_contract = SignalContract(
        symbol="XAUUSD",
        timeframe="M5",
        direction=SignalDirection.BUY,
        entry_price=2300.0,
        stop_loss=0.0,
        take_profit=0.0,
        lot_size=0.1,
        confidence=0.6,
        generated_at=context.candle_time,
        strategy_code="EMA_ATR_TREND",
        metadata={"signal_id": str(uuid.uuid4())},
    )
    context.ingestion_result = {"account_info": {"equity": 10000.0}, "symbol_info": {"trade_contract_size": 100.0}}
    context.regime_result = RegimeResult(regime=MarketRegimeType.TRENDING_BULLISH, confidence=0.6, is_tradeable=True, features={})

    engine = RiskEngine(risk_repository=RiskRepo())
    result = engine.run(context)
    assert result.rejected is True
    assert result.rejection_reason == "RISK_FAILED"


def test_execution_gate_rejects_when_broker_unhealthy() -> None:
    class ExecutionRepo:
        def __init__(self) -> None:
            self.session = DummySession()

        @staticmethod
        def create_execution_decision(**_kwargs):
            class R:
                id = uuid.uuid4()

            return R()

    class SafetyRepo:
        @staticmethod
        def get_active_kill_switch():
            return None

    context = _context()
    context.signal_contract = SignalContract(
        symbol="XAUUSD",
        timeframe="M5",
        direction=SignalDirection.BUY,
        entry_price=2301.0,
        stop_loss=2299.0,
        take_profit=2305.0,
        lot_size=0.1,
        confidence=0.7,
        generated_at=context.candle_time,
        strategy_code="EMA_ATR_TREND",
        metadata={"signal_id": str(uuid.uuid4())},
    )
    _attach_pre_execution_passed_fields(context)
    context.broker_health = BrokerHealth(is_healthy=False, is_connected=True, is_trade_allowed=True)

    engine = ExecutionGate(execution_repository=ExecutionRepo(), safety_repository=SafetyRepo())
    result = engine.run(context)
    assert result.rejected is True
    assert result.rejection_reason == "EXECUTION_GATE_REJECTED"
    assert result.execution_decision is not None
    assert result.execution_decision.status == ExecutionDecisionStatus.REJECTED


def test_demo_auto_rejects_real_account() -> None:
    class ExecutionRepo:
        def __init__(self) -> None:
            self.session = DummySession()

        @staticmethod
        def create_execution_decision(**_kwargs):
            class R:
                id = uuid.uuid4()

            return R()

    class SafetyRepo:
        @staticmethod
        def get_active_kill_switch():
            return None

    context = _context()
    context.ingestion_result = {
        "account_info": {"server": "Broker-Real", "name": "Real Account", "trade_mode": 2},
    }
    context.signal_contract = SignalContract(
        symbol="XAUUSD",
        timeframe="M5",
        direction=SignalDirection.BUY,
        entry_price=2301.0,
        stop_loss=2299.0,
        take_profit=2305.0,
        lot_size=0.1,
        confidence=0.7,
        generated_at=context.candle_time,
        strategy_code="EMA_ATR_TREND",
        metadata={"signal_id": str(uuid.uuid4())},
    )
    _attach_pre_execution_passed_fields(context)
    context.broker_health = BrokerHealth(is_healthy=True, is_connected=True, is_trade_allowed=True)

    class _Settings:
        auto_trade = True
        dry_run = True
        approval_required = False
        account_mode = "DEMO_AUTO"

    engine = ExecutionGate(execution_repository=ExecutionRepo(), safety_repository=SafetyRepo(), settings=_Settings())
    result = engine.run(context)
    assert result.rejected is True
    assert result.rejection_reason == "EXECUTION_GATE_REJECTED"
    assert result.execution_decision is not None
    assert result.execution_decision.reason == "DEMO_ACCOUNT_REQUIRED"


def test_execution_engine_does_not_order_send_in_dry_run() -> None:
    class ExecutionRepo:
        def __init__(self) -> None:
            self.session = DummySession()

        @staticmethod
        def create_execution_order(**_kwargs):
            class R:
                id = uuid.uuid4()

            return R()

        @staticmethod
        def update_execution_order_result(**_kwargs):
            return None

    class SafetyRepo:
        @staticmethod
        def get_active_kill_switch():
            return None

    class FakeOrderExecutor:
        def __init__(self) -> None:
            self.send_called = 0

        @staticmethod
        def build_market_order_request(signal: SignalContract, risk_plan: RiskPlan) -> dict:
            return {"symbol": signal.symbol, "volume": risk_plan.lot_size}

        def send_market_order(self, *_args, **_kwargs):
            self.send_called += 1
            raise AssertionError("send_market_order should not be called in DRY_RUN")

    context = _context()
    context.ingestion_result = {
        "symbol_id": uuid.uuid4(),
        "account_info": {"server": "Demo-Server", "name": "Demo Account", "trade_mode": 0},
    }
    context.signal_contract = SignalContract(
        symbol="XAUUSD",
        timeframe="M5",
        direction=SignalDirection.BUY,
        entry_price=2301.0,
        stop_loss=2299.0,
        take_profit=2305.0,
        lot_size=0.1,
        confidence=0.7,
        generated_at=context.candle_time,
        strategy_code="EMA_ATR_TREND",
        metadata={"signal_id": str(uuid.uuid4())},
    )
    context.risk_plan = RiskPlan(
        passed=True,
        lot_size=0.1,
        entry_price=2301.0,
        stop_loss=2299.0,
        take_profit=2305.0,
        risk_per_trade_pct=1.0,
        max_daily_loss_pct=5.0,
    )
    context.execution_decision = ExecutionDecision(status=ExecutionDecisionStatus.DRY_RUN, details={})

    fake_executor = FakeOrderExecutor()
    engine = ExecutionEngine(
        execution_repository=ExecutionRepo(),
        safety_repository=SafetyRepo(),
        order_executor=fake_executor,
    )
    result = engine.run(context)
    assert result.order_result is not None
    assert result.order_result.status == OrderExecutionStatus.DRY_RUN
    assert fake_executor.send_called == 0


def test_execution_engine_cannot_bypass_gate_without_approve_auto() -> None:
    class ExecutionRepo:
        def __init__(self) -> None:
            self.session = DummySession()

        @staticmethod
        def create_execution_order(**_kwargs):
            class R:
                id = uuid.uuid4()

            return R()

        @staticmethod
        def update_execution_order_result(**_kwargs):
            return None

    class SafetyRepo:
        @staticmethod
        def get_active_kill_switch():
            return None

    class FakeOrderExecutor:
        def __init__(self) -> None:
            self.send_called = 0

        @staticmethod
        def build_market_order_request(signal: SignalContract, risk_plan: RiskPlan) -> dict:
            return {"symbol": signal.symbol, "volume": risk_plan.lot_size}

        def send_market_order(self, *_args, **_kwargs):
            self.send_called += 1
            raise AssertionError("send_market_order should not be called")

    context = _context()
    context.ingestion_result = {"symbol_id": uuid.uuid4()}
    context.signal_contract = SignalContract(
        symbol="XAUUSD",
        timeframe="M5",
        direction=SignalDirection.BUY,
        entry_price=2301.0,
        stop_loss=2299.0,
        take_profit=2305.0,
        lot_size=0.1,
        confidence=0.7,
        generated_at=context.candle_time,
        strategy_code="EMA_ATR_TREND",
        metadata={"signal_id": str(uuid.uuid4())},
    )
    context.risk_plan = RiskPlan(
        passed=True,
        lot_size=0.1,
        entry_price=2301.0,
        stop_loss=2299.0,
        take_profit=2305.0,
        risk_per_trade_pct=1.0,
        max_daily_loss_pct=5.0,
    )
    context.execution_decision = ExecutionDecision(status=ExecutionDecisionStatus.REJECTED, details={})

    fake_executor = FakeOrderExecutor()
    engine = ExecutionEngine(
        execution_repository=ExecutionRepo(),
        safety_repository=SafetyRepo(),
        order_executor=fake_executor,
    )
    result = engine.run(context)

    assert result.rejected is True
    assert result.rejection_reason == "ORDER_EXECUTION_FAILED"
    assert fake_executor.send_called == 0


def test_kill_switch_monitor_blocks_active_kill_switch() -> None:
    class ActiveKill:
        id = uuid.uuid4()

    class SafetyRepo:
        def __init__(self) -> None:
            self.session = DummySession()

        @staticmethod
        def get_active_kill_switch():
            return ActiveKill()

        @staticmethod
        def create_safety_event(**_kwargs):
            return None

    context = _context()
    engine = KillSwitchMonitor(safety_repository=SafetyRepo())
    result = engine.run(context)
    assert result.rejected is True
    assert result.rejection_reason == "KILL_SWITCH_ACTIVE"


def test_mt5_adapter_only_in_infrastructure_layer() -> None:
    root = Path(__file__).resolve().parents[2]
    py_files = list((root / "src").rglob("*.py"))
    invalid: list[str] = []
    for file_path in py_files:
        text = file_path.read_text(encoding="utf-8")
        if "import MetaTrader5" in text:
            normalized = str(file_path).replace("\\", "/")
            if "/src/infrastructure/mt5/" not in normalized:
                invalid.append(normalized)
    assert invalid == []


def test_api_does_not_run_trading_logic() -> None:
    root = Path(__file__).resolve().parents[2]
    api_files = list((root / "src" / "api").rglob("*.py"))
    banned_tokens = ["TradingOrchestrator", "run_cycle(", "src.bot_worker"]
    offenders: list[str] = []
    for file_path in api_files:
        text = file_path.read_text(encoding="utf-8")
        if any(token in text for token in banned_tokens):
            offenders.append(str(file_path))
    assert offenders == []
