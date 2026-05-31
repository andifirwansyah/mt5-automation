"""Signal contract builder engine."""

from __future__ import annotations

import uuid

from src.domain.models.signal import SignalContract
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories.signal_repository import SignalRepository
from src.repositories.strategy_repository import StrategyRepository


class SignalContractBuilder(PipelineStep):
    """Convert raw signal into normalized signal contract and persist it."""

    @property
    def name(self) -> str:
        return "SignalContractBuilder"

    def __init__(self, signal_repository: SignalRepository, strategy_repository: StrategyRepository, default_lot_size: float = 0.1) -> None:
        self.signal_repository = signal_repository
        self.strategy_repository = strategy_repository
        self.default_lot_size = default_lot_size

    @staticmethod
    def _as_uuid(value: object) -> uuid.UUID | None:
        if isinstance(value, uuid.UUID):
            return value
        if isinstance(value, str) and value:
            try:
                return uuid.UUID(value)
            except ValueError:
                return None
        return None

    def run(self, context: TradingContext) -> TradingContext:
        if context.raw_signal is None or context.strategy_selection is None:
            context.reject("NO_RAW_SIGNAL", {"message": "raw_signal and strategy_selection are required"})
            return context

        raw = context.raw_signal
        strategy_code = context.strategy_selection.strategy_code
        lot_size = float(context.strategy_selection.config.get("lot_size", self.default_lot_size))

        contract = SignalContract(
            symbol=context.symbol,
            timeframe=context.timeframe,
            direction=raw.direction,
            entry_price=raw.entry_price,
            stop_loss=raw.stop_loss,
            take_profit=raw.take_profit,
            lot_size=lot_size,
            confidence=raw.confidence,
            generated_at=raw.generated_at,
            strategy_code=strategy_code,
            metadata={
                "side": raw.direction.value,
                "entry_type": "MARKET",
                "reason": context.strategy_selection.reason,
                "features": raw.features,
            },
        )
        context.signal_contract = contract

        ingestion = context.ingestion_result or {}
        symbol_id = self._as_uuid(ingestion.get("symbol_id"))
        timeframe_id = self._as_uuid((ingestion.get("timeframe_ids") or {}).get(context.timeframe))
        strategy_id = self._as_uuid((context.strategy_selection.details or {}).get("strategy_id"))

        if symbol_id is None or timeframe_id is None:
            context.reject("SIGNAL_CONTRACT_FAILED", {"message": "symbol/timeframe references missing"})
            return context

        if strategy_id is None:
            active_strategies = self.strategy_repository.get_active_strategies()
            matched = next((s for s in active_strategies if s.code.upper() == strategy_code.upper()), None)
            if matched is None:
                context.reject("SIGNAL_CONTRACT_FAILED", {"message": f"strategy_id not found for code={strategy_code}"})
                return context
            strategy_id = matched.id

        signal_row = self.signal_repository.create_signal(
            trace_id=context.trace_id,
            symbol_id=symbol_id,
            timeframe_id=timeframe_id,
            strategy_id=strategy_id,
            direction=raw.direction.value,
            status="GENERATED",
            signal_time=raw.generated_at,
            entry_price=raw.entry_price,
            stop_loss=raw.stop_loss,
            take_profit=raw.take_profit,
            lot_size=lot_size,
            confidence=raw.confidence,
            features=raw.features,
            raw_payload={
                "reason": context.strategy_selection.reason,
                "entry_type": "MARKET",
                "metadata": raw.metadata,
            },
        )
        self.signal_repository.session.commit()

        context.signal_contract.metadata["signal_id"] = str(signal_row.id)
        return context
