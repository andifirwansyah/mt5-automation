"""Core end-to-end pipeline orchestrator service."""

from dataclasses import asdict
from datetime import UTC, datetime

import pandas as pd

from ai_trading_automation.modules.execution_gate import (
    ExecutionGateRequest,
    ExecutionGateService,
)
from ai_trading_automation.modules.market_data import DatasetLoadRequest, MarketDataLoaderService
from ai_trading_automation.modules.market_regime import MarketRegimeRequest, MarketRegimeService
from ai_trading_automation.modules.ohlcv_validation import (
    OHLCVValidationRequest,
    OHLCVValidationService,
)
from ai_trading_automation.modules.paper_execution import (
    CreatePaperOrderRequest,
    PaperExecutionBlockedError,
    PaperExecutionService,
)
from ai_trading_automation.modules.performance_analyzer import (
    PerformanceAnalysisRequest,
    PerformanceAnalyzerService,
)
from ai_trading_automation.modules.position_monitor import (
    MarketCandle,
    PositionMonitorRequest,
    PositionMonitorService,
)
from ai_trading_automation.modules.pre_trade_simulation import (
    PreTradeSimulationRequest,
    PreTradeSimulationService,
)
from ai_trading_automation.modules.risk_engine import RiskEngineRequest, RiskEngineService
from ai_trading_automation.modules.risk_engine.models import RiskPlan
from ai_trading_automation.modules.signal_contract import (
    SignalContractBuildRequest,
    SignalContractService,
)
from ai_trading_automation.modules.signal_validator import (
    SignalValidationRequest,
    SignalValidatorService,
)
from ai_trading_automation.modules.strategy_engine import StrategyEngineRequest, StrategyEngineService
from ai_trading_automation.modules.strategy_selector import (
    StrategySelectorRequest,
    StrategySelectorService,
)
from ai_trading_automation.modules.trade_journal import (
    JournalReadRequest,
    JournalWriteRequest,
    TradeJournalService,
)

from .contracts import PipelineRunRequest
from .models import PipelineRunResult


class PipelineOrchestratorService:
    """Run full pipeline using existing module services in sequence."""

    def __init__(
        self,
        market_data_service: MarketDataLoaderService | None = None,
        ohlcv_validation_service: OHLCVValidationService | None = None,
        market_regime_service: MarketRegimeService | None = None,
        strategy_selector_service: StrategySelectorService | None = None,
        strategy_engine_service: StrategyEngineService | None = None,
        signal_contract_service: SignalContractService | None = None,
        signal_validator_service: SignalValidatorService | None = None,
        risk_engine_service: RiskEngineService | None = None,
        pre_trade_simulation_service: PreTradeSimulationService | None = None,
        execution_gate_service: ExecutionGateService | None = None,
        paper_execution_service: PaperExecutionService | None = None,
        position_monitor_service: PositionMonitorService | None = None,
        trade_journal_service: TradeJournalService | None = None,
        performance_analyzer_service: PerformanceAnalyzerService | None = None,
    ) -> None:
        self.market_data_service = market_data_service or MarketDataLoaderService()
        self.ohlcv_validation_service = ohlcv_validation_service or OHLCVValidationService()
        self.market_regime_service = market_regime_service or MarketRegimeService()
        self.strategy_selector_service = strategy_selector_service or StrategySelectorService()
        self.strategy_engine_service = strategy_engine_service or StrategyEngineService()
        self.signal_contract_service = signal_contract_service or SignalContractService()
        self.signal_validator_service = signal_validator_service or SignalValidatorService()
        self.risk_engine_service = risk_engine_service or RiskEngineService()
        self.pre_trade_simulation_service = pre_trade_simulation_service or PreTradeSimulationService()
        self.execution_gate_service = execution_gate_service or ExecutionGateService()
        self.paper_execution_service = paper_execution_service or PaperExecutionService()
        self.position_monitor_service = position_monitor_service or PositionMonitorService()
        self.trade_journal_service = trade_journal_service or TradeJournalService()
        self.performance_analyzer_service = performance_analyzer_service or PerformanceAnalyzerService()

    def run(self, request: PipelineRunRequest) -> PipelineRunResult:
        """Run full deterministic pipeline end-to-end."""
        stage = "market_data"
        artifacts: dict[str, object] = {}
        now = datetime.now(tz=UTC)

        try:
            raw_frame = self.market_data_service.load_timeframe(
                DatasetLoadRequest(
                    dataset_path=request.dataset_path,
                    symbol=request.symbol,
                    timeframe=request.timeframe,
                )
            )
            artifacts["raw_frame_rows"] = len(raw_frame.frame.index)

            stage = "ohlcv_validation"
            validation_output = self.ohlcv_validation_service.validate(
                OHLCVValidationRequest(raw_frame=raw_frame)
            )
            artifacts["ohlcv_validation"] = asdict(validation_output.result)
            if not validation_output.result.is_valid or validation_output.validated_frame is None:
                return PipelineRunResult(
                    success=False,
                    stage=stage,
                    message="OHLCV validation failed.",
                    decision=None,
                    run_at=now,
                    artifacts=artifacts,
                )

            validated_frame = validation_output.validated_frame

            stage = "market_regime"
            regime_result = self.market_regime_service.detect(
                MarketRegimeRequest(primary_frame=validated_frame)
            )
            artifacts["market_regime"] = asdict(regime_result)

            stage = "strategy_selector"
            selected_strategy = self.strategy_selector_service.select(
                StrategySelectorRequest(market_regime=regime_result)
            )
            artifacts["selected_strategy"] = asdict(selected_strategy)

            stage = "strategy_engine"
            raw_signal = self.strategy_engine_service.execute(
                StrategyEngineRequest(
                    selected_strategy=selected_strategy,
                    market_frame=validated_frame,
                )
            )

            stage = "signal_contract"
            signal_metadata = dict(raw_signal.metadata)
            signal_metadata = self._enrich_signal_price_fields(
                raw_signal_direction=raw_signal.direction,
                frame=validated_frame.frame,
                metadata=signal_metadata,
            )
            raw_signal.metadata = signal_metadata
            signal_contract = self.signal_contract_service.build(
                SignalContractBuildRequest(raw_candidate=raw_signal)
            )
            artifacts["signal"] = signal_contract.model_dump()

            stage = "signal_validator"
            signal_validation = self.signal_validator_service.validate(
                SignalValidationRequest(signal=signal_contract, market_regime=regime_result)
            )
            artifacts["signal_validation"] = asdict(signal_validation)

            stage = "risk_engine"
            if signal_validation.is_valid and signal_contract.direction in {"BUY", "SELL"}:
                risk_plan = self.risk_engine_service.calculate(
                    RiskEngineRequest(
                        signal=signal_contract,
                        account_balance=request.account_balance,
                        daily_realized_loss=request.daily_realized_loss,
                        open_positions_count=request.open_positions_count,
                        requested_risk_percent=request.requested_risk_percent,
                    )
                )
            else:
                risk_plan = self._fallback_risk_plan(requested_risk_percent=request.requested_risk_percent)
                artifacts["risk_engine_skipped"] = (
                    "Risk calculation skipped because signal is not tradable (WAIT/invalid)."
                )
            artifacts["risk_plan"] = asdict(risk_plan)

            stage = "pre_trade_simulation"
            simulation_result = self.pre_trade_simulation_service.run(
                PreTradeSimulationRequest(
                    signal_validation=signal_validation,
                    risk_plan=risk_plan,
                )
            )
            artifacts["simulation_result"] = asdict(simulation_result)

            stage = "execution_gate"
            execution_decision = self.execution_gate_service.decide(
                ExecutionGateRequest(
                    signal_validation=signal_validation,
                    risk_plan=risk_plan,
                    simulation_result=simulation_result,
                )
            )
            artifacts["execution_decision"] = asdict(execution_decision)

            stage = "paper_execution"
            paper_order = None
            try:
                paper_order = self.paper_execution_service.create_order(
                    CreatePaperOrderRequest(execution_decision=execution_decision)
                )
            except PaperExecutionBlockedError:
                paper_order = None
            artifacts["paper_order"] = asdict(paper_order) if paper_order is not None else None

            stage = "position_monitor"
            position_state = None
            if paper_order is not None:
                latest = validated_frame.frame.iloc[-1]
                position_state = self.position_monitor_service.update(
                    PositionMonitorRequest(
                        order=paper_order,
                        candle=MarketCandle(
                            timestamp=self._to_datetime(latest["timestamp"]),
                            open=float(latest["open"]),
                            high=float(latest["high"]),
                            low=float(latest["low"]),
                            close=float(latest["close"]),
                        ),
                    )
                )
                self.paper_execution_service.sync_position_state(
                    order_id=paper_order.order_id,
                    position_state=position_state,
                )
            artifacts["position_state"] = asdict(position_state) if position_state is not None else None

            stage = "trade_journal"
            journal_entry = self.trade_journal_service.write_entry(
                JournalWriteRequest(
                    signal_validation=signal_validation,
                    risk_plan=risk_plan,
                    simulation_result=simulation_result,
                    execution_decision=execution_decision,
                    order_state=paper_order,
                    result=position_state,
                    notes=["orchestrator_pipeline_run"],
                    closed_at=position_state.updated_at if position_state and position_state.status == "CLOSED" else None,
                )
            )
            artifacts["journal_id"] = journal_entry.journal_id

            stage = "performance_analyzer"
            entries = self.trade_journal_service.read_entries(
                JournalReadRequest(journal_path=self.trade_journal_service.journal_path)
            )
            performance_report = self.performance_analyzer_service.analyze(
                PerformanceAnalysisRequest(
                    entries=entries,
                    persist_report=request.persist_performance_report,
                )
            )
            artifacts["performance_report"] = asdict(performance_report)

            return PipelineRunResult(
                success=True,
                stage="completed",
                message="Pipeline run completed.",
                decision=execution_decision.decision,
                run_at=now,
                artifacts=artifacts,
            )
        except Exception as error:
            artifacts["error"] = str(error)
            return PipelineRunResult(
                success=False,
                stage=stage,
                message=f"Pipeline failed at stage '{stage}': {error}",
                decision=None,
                run_at=now,
                artifacts=artifacts,
            )

    def _to_datetime(self, value: object) -> datetime:
        if isinstance(value, datetime):
            return value
        timestamp = pd.to_datetime(value, errors="coerce")
        if pd.isna(timestamp):
            return datetime.now(tz=UTC)
        if hasattr(timestamp, "to_pydatetime"):
            return timestamp.to_pydatetime()
        return datetime.now(tz=UTC)

    def _enrich_signal_price_fields(
        self,
        raw_signal_direction: str,
        frame: pd.DataFrame,
        metadata: dict[str, str | float | int | bool],
    ) -> dict[str, str | float | int | bool]:
        if raw_signal_direction == "WAIT":
            return metadata

        last_row = frame.iloc[-1]
        entry_price = float(last_row["close"])
        avg_range = float((frame["high"] - frame["low"]).abs().mean())
        buffer = max(avg_range * 1.5, entry_price * 0.001)

        if raw_signal_direction == "BUY":
            stop_loss = entry_price - buffer
            take_profit = entry_price + (buffer * 2.0)
        else:
            stop_loss = entry_price + buffer
            take_profit = entry_price - (buffer * 2.0)

        metadata.setdefault("entry_price", round(entry_price, 6))
        metadata.setdefault("stop_loss", round(stop_loss, 6))
        metadata.setdefault("take_profit", round(take_profit, 6))
        return metadata

    def _fallback_risk_plan(self, requested_risk_percent: float) -> RiskPlan:
        """Return neutral risk plan when signal is not tradable."""
        return RiskPlan(
            risk_amount=0.0,
            risk_percent=max(0.0, float(requested_risk_percent)),
            lot_size=0.0,
            stop_loss=0.0,
            risk_reward_ratio=0.0,
            max_loss=0.0,
            notes=["Fallback risk plan for non-tradable signal."],
        )
