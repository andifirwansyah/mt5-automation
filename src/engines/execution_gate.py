"""Execution gate engine for final trading decision."""

from __future__ import annotations

import uuid

from src.config.settings import AppSettings, get_settings
from src.domain.enums import ExecutionDecisionStatus
from src.domain.models.execution_decision import ExecutionDecision
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories.execution_repository import ExecutionRepository
from src.repositories.safety_repository import SafetyRepository


class ExecutionGate(PipelineStep):
    """Approve/reject execution based on all upstream safety checks."""

    @property
    def name(self) -> str:
        return "ExecutionGate"

    def __init__(
        self,
        execution_repository: ExecutionRepository,
        safety_repository: SafetyRepository,
        settings: AppSettings | None = None,
    ) -> None:
        self.execution_repository = execution_repository
        self.safety_repository = safety_repository
        self.settings = settings or get_settings()

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
    def _is_demo_account(account_info: dict | None) -> tuple[bool, dict]:
        info = account_info or {}
        server = str(info.get("server", ""))
        name = str(info.get("name", ""))
        trade_mode = info.get("trade_mode")

        is_demo_by_server = "demo" in server.lower()
        is_demo_by_name = "demo" in name.lower()
        is_demo_by_trade_mode = False
        if trade_mode is not None:
            try:
                is_demo_by_trade_mode = int(trade_mode) == 0
            except (TypeError, ValueError):
                is_demo_by_trade_mode = False

        is_demo = bool(is_demo_by_server or is_demo_by_name or is_demo_by_trade_mode)
        return is_demo, {
            "server": server,
            "name": name,
            "trade_mode": trade_mode,
            "is_demo_by_server": is_demo_by_server,
            "is_demo_by_name": is_demo_by_name,
            "is_demo_by_trade_mode": is_demo_by_trade_mode,
        }

    def run(self, context: TradingContext) -> TradingContext:
        def db_decision_code(status: ExecutionDecisionStatus) -> str:
            mapping = {
                ExecutionDecisionStatus.APPROVE_AUTO: "APPROVE_AUTO",
                ExecutionDecisionStatus.DRY_RUN: "DRY_RUN",
                ExecutionDecisionStatus.REQUIRE_MANUAL_APPROVAL: "MANUAL_APPROVAL",
                ExecutionDecisionStatus.REJECTED: "REJECT",
                ExecutionDecisionStatus.KILL_SWITCH_ACTIVE: "KILL_SWITCH",
                ExecutionDecisionStatus.APPROVED: "APPROVED",
            }
            return mapping.get(status, "REJECT")

        signal = context.signal_contract
        signal_id = self._as_uuid(signal.metadata.get("signal_id") if signal else None)
        if signal_id is None:
            context.reject("EXECUTION_GATE_REJECTED", {"message": "signal_id missing"})
            return context

        kill_switch_active = self.safety_repository.get_active_kill_switch() is not None
        if kill_switch_active:
            status = ExecutionDecisionStatus.KILL_SWITCH_ACTIVE
            decision = ExecutionDecision(status=status, reason="KILL_SWITCH_ACTIVE", details={"kill_switch": True})
            context.execution_decision = decision

            row = self.execution_repository.create_execution_decision(
                signal_id=signal_id,
                trace_id=context.trace_id,
                decision=db_decision_code(status),
                rejection_reason="KILL_SWITCH_ACTIVE",
                details=decision.details,
            )
            self.execution_repository.session.commit()
            context.execution_decision.details["execution_decision_id"] = str(row.id)
            context.reject("KILL_SWITCH_ACTIVE", {"message": "Kill switch active"})
            return context

        account_mode = str(getattr(self.settings, "account_mode", "DEMO_AUTO") or "DEMO_AUTO").upper()
        if account_mode == "DEMO_AUTO":
            account_info = (context.ingestion_result or {}).get("account_info") or {}
            is_demo, demo_details = self._is_demo_account(account_info)
            if not is_demo:
                decision = ExecutionDecision(
                    status=ExecutionDecisionStatus.REJECTED,
                    reason="DEMO_ACCOUNT_REQUIRED",
                    details={"account_mode": account_mode, "demo_lock": demo_details},
                )
                context.execution_decision = decision

                row = self.execution_repository.create_execution_decision(
                    signal_id=signal_id,
                    trace_id=context.trace_id,
                    decision=db_decision_code(ExecutionDecisionStatus.REJECTED),
                    rejection_reason="DEMO_ACCOUNT_REQUIRED",
                    details=decision.details,
                )
                self.execution_repository.session.commit()
                context.execution_decision.details["execution_decision_id"] = str(row.id)
                context.reject("EXECUTION_GATE_REJECTED", {"message": "Demo account required for DEMO_AUTO", **decision.details})
                return context

        checks_passed = all(
            [
                context.data_quality_result is not None and context.data_quality_result.passed,
                context.market_event_result is not None and context.market_event_result.passed,
                context.regime_result is not None and context.regime_result.is_tradeable,
                context.signal_validation is not None and context.signal_validation.passed,
                context.historical_edge is not None and context.historical_edge.passed,
                context.risk_plan is not None and context.risk_plan.passed,
                context.simulation_result is not None and context.simulation_result.passed,
                context.broker_health is not None and context.broker_health.is_healthy,
            ]
        )

        if not bool(self.settings.auto_trade):
            decision_status = ExecutionDecisionStatus.REJECTED
            decision_reason = "AUTO_TRADE_DISABLED"
        elif not checks_passed:
            decision_status = ExecutionDecisionStatus.REJECTED
            decision_reason = "EXECUTION_CHECKS_FAILED"
        elif bool(self.settings.dry_run):
            decision_status = ExecutionDecisionStatus.DRY_RUN
            decision_reason = None
        elif bool(self.settings.approval_required):
            decision_status = ExecutionDecisionStatus.REQUIRE_MANUAL_APPROVAL
            decision_reason = None
        else:
            decision_status = ExecutionDecisionStatus.APPROVE_AUTO
            decision_reason = None

        decision = ExecutionDecision(
            status=decision_status,
            reason=decision_reason,
            details={
                "auto_trade": self.settings.auto_trade,
                "dry_run": self.settings.dry_run,
                "approval_required": self.settings.approval_required,
                "checks_passed": checks_passed,
            },
        )
        context.execution_decision = decision

        row = self.execution_repository.create_execution_decision(
            signal_id=signal_id,
            trace_id=context.trace_id,
            decision=db_decision_code(decision_status),
            rejection_reason=decision_reason,
            details=decision.details,
        )
        self.execution_repository.session.commit()
        context.execution_decision.details["execution_decision_id"] = str(row.id)

        if decision_status == ExecutionDecisionStatus.REJECTED:
            context.reject("EXECUTION_GATE_REJECTED", decision.details)
        return context
