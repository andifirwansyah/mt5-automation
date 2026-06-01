"""Trade journal engine for auditable pipeline lifecycle records."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories.journal_repository import JournalRepository


class TradeJournalEngine(PipelineStep):
    """Persist important trading lifecycle events into trade_journals."""

    @property
    def name(self) -> str:
        return "TradeJournalEngine"

    def __init__(self, journal_repository: JournalRepository) -> None:
        self.journal_repository = journal_repository

    def _to_json_safe(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(k): self._to_json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._to_json_safe(v) for v in value]
        if is_dataclass(value):
            return self._to_json_safe(asdict(value))
        return str(value)

    def _technical_summary(self, context: TradingContext) -> dict[str, Any]:
        technical = context.technical_analysis
        contract_summary = {}
        if context.signal_contract is not None:
            contract_summary = (context.signal_contract.metadata or {}).get("technical_summary", {}) or {}

        if technical is None and not contract_summary:
            return {}

        active_patterns = contract_summary.get("active_patterns") if isinstance(contract_summary, dict) else None
        fvg_summary = contract_summary.get("fvg_summary") if isinstance(contract_summary, dict) else None
        setup_signature = contract_summary.get("setup_signature") if isinstance(contract_summary, dict) else None

        return {
            "bias": getattr(technical, "bias", None) or contract_summary.get("technical_bias"),
            "score": getattr(technical, "technical_score", None) or contract_summary.get("technical_score"),
            "buy_score": getattr(technical, "buy_score", None) or contract_summary.get("buy_score"),
            "sell_score": getattr(technical, "sell_score", None) or contract_summary.get("sell_score"),
            "active_patterns": active_patterns or [],
            "fvg_summary": fvg_summary or {},
            "setup_signature": setup_signature,
            "warnings": list(getattr(technical, "warnings", []) or contract_summary.get("warnings", [])),
            "strategy_hints": list(getattr(technical, "strategy_hints", [])),
            "conflict_flags": list(getattr(technical, "conflict_flags", [])),
        }

    def _pipeline_blockers(self, context: TradingContext) -> list[str]:
        blockers: list[str] = []
        if context.strategy_selection is None:
            blockers.append("no_strategy_selected")
        if context.signal_validation is not None and not context.signal_validation.passed:
            blockers.append("signal_validator_conflict")
        if context.historical_edge is not None and not context.historical_edge.passed:
            blockers.append("historical_edge_insufficient")
        if context.risk_plan is not None and not context.risk_plan.passed:
            blockers.append("risk_invalid")
        if context.execution_decision is not None and str(context.execution_decision.status.value) in ("REJECTED", "REQUIRE_MANUAL_APPROVAL", "KILL_SWITCH_ACTIVE"):
            blockers.append("execution_gate_blocked")
        if context.approval_result is not None and not context.approval_result.passed:
            blockers.append("approval_not_granted")
        return blockers

    def run(self, context: TradingContext) -> TradingContext:
        full_context = self._to_json_safe(asdict(context))
        technical_summary = self._technical_summary(context)
        selected_strategy = context.strategy_selection.strategy_code if context.strategy_selection else None
        blockers = self._pipeline_blockers(context)

        if context.rejected:
            self.journal_repository.create_trade_journal(
                journal_type="SIGNAL_REJECTION",
                message=f"Pipeline rejected: {context.rejection_reason}",
                trace_id=context.trace_id,
                details={
                    "rejection_reason": context.rejection_reason,
                    "rejection_details": self._to_json_safe(context.rejection_details or {}),
                    "selected_strategy": selected_strategy,
                    "technical_summary": technical_summary,
                    "pipeline_blockers": blockers,
                    "full_context": full_context,
                },
            )

        if context.execution_decision is not None:
            self.journal_repository.create_trade_journal(
                journal_type="EXECUTION_DECISION",
                message=f"Execution decision: {context.execution_decision.status.value}",
                trace_id=context.trace_id,
                details={
                    "decision": context.execution_decision.status.value,
                    "reason": context.execution_decision.reason,
                    "details": self._to_json_safe(context.execution_decision.details),
                    "selected_strategy": selected_strategy,
                    "technical_summary": technical_summary,
                    "rejection_reason": context.rejection_reason,
                    "pipeline_blockers": blockers,
                    "full_context": full_context,
                },
            )

        if context.order_result is not None:
            self.journal_repository.create_trade_journal(
                journal_type="ORDER_EXECUTION",
                message=f"Order status: {context.order_result.status.value}",
                trace_id=context.trace_id,
                details={
                    "order_status": context.order_result.status.value,
                    "order_ticket": context.order_result.order_ticket,
                    "error_message": context.order_result.error_message,
                    "request_payload": self._to_json_safe(context.order_result.request_payload),
                    "response_payload": self._to_json_safe(context.order_result.response_payload),
                    "selected_strategy": selected_strategy,
                    "technical_summary": technical_summary,
                    "rejection_reason": context.rejection_reason,
                    "pipeline_blockers": blockers,
                    "full_context": full_context,
                },
            )

        closed_count = int(((context.ingestion_result or {}).get("position_monitor") or {}).get("closed_positions", 0))
        if closed_count > 0:
            self.journal_repository.create_trade_journal(
                journal_type="CLOSED_TRADE",
                message=f"Detected {closed_count} closed positions",
                trace_id=context.trace_id,
                details={"closed_positions": closed_count, "full_context": full_context},
            )

        self.journal_repository.session.commit()
        return context
