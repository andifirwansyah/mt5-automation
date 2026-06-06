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

    @staticmethod
    def _build_technical_summary(context: TradingContext) -> dict:
        technical = context.technical_analysis
        if technical is None:
            return {}

        active_patterns: list[str] = []
        fvg_status_count = {"open": 0, "partial": 0, "filled": 0}
        fvg_type_count = {"bullish_fvg": 0, "bearish_fvg": 0}

        for evidence in technical.pattern_evidence:
            if evidence.pattern_type in ("DOUBLE_TOP", "DOUBLE_BOTTOM"):
                status = str((evidence.details or {}).get("status", "unknown")).lower()
                pattern_name = evidence.pattern_type.lower()
                active_patterns.append(f"{pattern_name}_{status}")
            if evidence.pattern_type == "FVG":
                for fvg in evidence.fvgs:
                    fvg_status_count[fvg.status] = fvg_status_count.get(fvg.status, 0) + 1
                    fvg_type_count[fvg.type] = fvg_type_count.get(fvg.type, 0) + 1
                    active_patterns.append(f"{fvg.type}_{fvg.status}")

        setup_key = active_patterns[0] if active_patterns else "no_pattern"
        setup_signature = f"{context.strategy_selection.strategy_code}:{setup_key}:{context.symbol}:{context.timeframe}"

        return {
            "technical_bias": technical.bias,
            "technical_score": technical.technical_score,
            "buy_score": technical.buy_score,
            "sell_score": technical.sell_score,
            "active_patterns": active_patterns,
            "fvg_summary": {
                "count": fvg_status_count["open"] + fvg_status_count["partial"] + fvg_status_count["filled"],
                "status_count": fvg_status_count,
                "type_count": fvg_type_count,
            },
            "warnings": list(technical.warnings),
            "setup_signature": setup_signature,
        }

    @staticmethod
    def _build_market_structure_summary(context: TradingContext) -> dict:
        structure = context.market_structure
        if structure is None:
            return {}
        return structure.to_summary()

    def run(self, context: TradingContext) -> TradingContext:
        if context.raw_signal is None or context.strategy_selection is None:
            context.reject("NO_RAW_SIGNAL", {"message": "raw_signal and strategy_selection are required"})
            return context

        raw = context.raw_signal
        strategy_code = context.strategy_selection.strategy_code
        lot_size = float(context.strategy_selection.config.get("lot_size", self.default_lot_size))
        technical_summary = self._build_technical_summary(context)
        market_structure_summary = self._build_market_structure_summary(context)

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
                "technical_summary": technical_summary,
                "market_structure_summary": market_structure_summary,
                "setup_signature": technical_summary.get("setup_signature"),
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
                "technical_summary": technical_summary,
                "market_structure_summary": market_structure_summary,
                "setup_signature": technical_summary.get("setup_signature"),
            },
        )
        self.signal_repository.session.commit()

        context.signal_contract.metadata["signal_id"] = str(signal_row.id)
        return context
