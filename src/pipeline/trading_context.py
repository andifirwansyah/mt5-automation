"""Shared state container for sequential trading pipeline."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.domain.models import (
    BrokerHealth,
    EdgeResult,
    ExecutionDecision,
    MarketSnapshot,
    OrderResult,
    RawSignal,
    RegimeResult,
    RiskPlan,
    SignalContract,
    SimulationResult,
    StrategySelectionResult,
    ValidationResult,
)


@dataclass(slots=True)
class TradingContext:
    """State bag passed through all pipeline steps."""

    trace_id: uuid.UUID
    symbol: str
    timeframe: str
    candle_time: datetime
    market_snapshot: MarketSnapshot | None = None
    ingestion_result: dict[str, Any] | None = None
    data_quality_result: ValidationResult | None = None
    market_event_result: ValidationResult | None = None
    regime_result: RegimeResult | None = None
    strategy_selection: StrategySelectionResult | None = None
    raw_signal: RawSignal | None = None
    signal_contract: SignalContract | None = None
    signal_validation: ValidationResult | None = None
    historical_edge: EdgeResult | None = None
    risk_plan: RiskPlan | None = None
    simulation_result: SimulationResult | None = None
    broker_health: BrokerHealth | None = None
    execution_decision: ExecutionDecision | None = None
    approval_result: ValidationResult | None = None
    order_result: OrderResult | None = None
    rejected: bool = False
    rejection_reason: str | None = None
    rejection_details: dict[str, Any] | None = None

    @classmethod
    def from_candle_event(cls, event: dict[str, Any]) -> "TradingContext":
        """Factory method to build context from incoming candle event payload."""

        symbol = str(event["symbol"])
        timeframe = str(event["timeframe"])
        candle_time = event.get("candle_time") or event.get("timestamp") or datetime.now(timezone.utc)
        if isinstance(candle_time, str):
            normalized = candle_time.replace("Z", "+00:00")
            candle_time = datetime.fromisoformat(normalized)

        snapshot = MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            candle_time=candle_time,
            open_price=float(event.get("open_price", event.get("open", 0.0))),
            high_price=float(event.get("high_price", event.get("high", 0.0))),
            low_price=float(event.get("low_price", event.get("low", 0.0))),
            close_price=float(event.get("close_price", event.get("close", 0.0))),
            tick_volume=int(event.get("tick_volume", 0)),
            spread=event.get("spread"),
            bid=event.get("bid"),
            ask=event.get("ask"),
            raw_payload=dict(event),
        )

        return cls(
            trace_id=uuid.uuid4(),
            symbol=symbol,
            timeframe=timeframe,
            candle_time=candle_time,
            market_snapshot=snapshot,
            ingestion_result={"source": event.get("source", "candle_event")},
        )

    def reject(self, reason: str, details: dict[str, Any] | None = None) -> None:
        """Mark context as rejected and store explicit reason/details."""

        self.rejected = True
        self.rejection_reason = reason
        self.rejection_details = details or {}
