"""Runtime state updater engine."""

from __future__ import annotations

from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.services.runtime_state_service import RuntimeStateService


class RuntimeStateUpdater(PipelineStep):
    """Persist important runtime markers for restart/recovery safety."""

    @property
    def name(self) -> str:
        return "RuntimeStateUpdater"

    def __init__(self, runtime_state_service: RuntimeStateService) -> None:
        self.runtime_state_service = runtime_state_service

    def run(self, context: TradingContext) -> TradingContext:
        self.runtime_state_service.set_last_processed_candle(
            symbol=context.symbol,
            timeframe=context.timeframe,
            candle_time=context.candle_time,
        )

        if context.signal_contract is not None:
            signal_id = context.signal_contract.metadata.get("signal_id")
            if signal_id:
                self.runtime_state_service.set_state("last_signal_id", str(signal_id))

        if context.order_result is not None:
            if context.order_result.order_ticket is not None:
                self.runtime_state_service.set_state("last_order_id", str(context.order_result.order_ticket))

        cycle_status = "REJECTED" if context.rejected else "SUCCESS"
        self.runtime_state_service.set_state("last_cycle_status", cycle_status)
        return context
