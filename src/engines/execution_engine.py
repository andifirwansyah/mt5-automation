"""Execution engine to place or skip orders based on execution decision."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.config.settings import AppSettings, get_settings
from src.domain.enums import ExecutionDecisionStatus, OrderExecutionStatus
from src.domain.models.order_result import OrderResult
from src.infrastructure.mt5.mt5_order_executor import MT5OrderExecutor
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories.execution_repository import ExecutionRepository
from src.repositories.safety_repository import SafetyRepository


class ExecutionEngine(PipelineStep):
    """Final order execution engine with strict safety guardrails."""

    @property
    def name(self) -> str:
        return "ExecutionEngine"

    def __init__(
        self,
        execution_repository: ExecutionRepository,
        safety_repository: SafetyRepository,
        order_executor: MT5OrderExecutor,
        settings: AppSettings | None = None,
    ) -> None:
        self.execution_repository = execution_repository
        self.safety_repository = safety_repository
        self.order_executor = order_executor
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
    def _now() -> datetime:
        return datetime.now(timezone.utc)

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
        decision = context.execution_decision
        signal = context.signal_contract
        risk_plan = context.risk_plan

        if decision is None or signal is None or risk_plan is None:
            context.reject("ORDER_EXECUTION_FAILED", {"message": "execution_decision/signal/risk_plan missing"})
            return context

        if self.safety_repository.get_active_kill_switch() is not None:
            context.reject("ORDER_EXECUTION_FAILED", {"message": "kill switch active"})
            return context

        if risk_plan.stop_loss <= 0 or risk_plan.take_profit <= 0:
            context.reject("ORDER_EXECUTION_FAILED", {"message": "SL/TP must be present and > 0"})
            return context

        signal_id = self._as_uuid(signal.metadata.get("signal_id"))
        symbol_id = self._as_uuid((context.ingestion_result or {}).get("symbol_id"))
        decision_id = self._as_uuid((decision.details or {}).get("execution_decision_id"))

        if signal_id is None or symbol_id is None:
            context.reject("ORDER_EXECUTION_FAILED", {"message": "signal_id/symbol_id missing for execution order"})
            return context

        account_mode = str(getattr(self.settings, "account_mode", "DEMO_AUTO") or "DEMO_AUTO").upper()
        account_info = (context.ingestion_result or {}).get("account_info") or {}
        if account_mode == "DEMO_AUTO":
            is_demo, demo_details = self._is_demo_account(account_info)
            if not is_demo:
                self.execution_repository.create_execution_order(
                    signal_id=signal_id,
                    execution_decision_id=decision_id,
                    symbol_id=symbol_id,
                    side=signal.direction.value,
                    order_type="MARKET",
                    volume_lot=risk_plan.lot_size,
                    requested_price=signal.entry_price,
                    stop_loss=risk_plan.stop_loss,
                    take_profit=risk_plan.take_profit,
                    deviation=int(self.settings.order_deviation),
                    status=OrderExecutionStatus.REJECTED.value,
                    broker_response={"request": {}, "response": {}},
                    error_message="DEMO_ACCOUNT_REQUIRED",
                    executed_at=self._now(),
                )
                self.execution_repository.session.commit()
                context.reject(
                    "ORDER_EXECUTION_FAILED",
                    {"message": "Demo account required for DEMO_AUTO", "rejection_reason": "DEMO_ACCOUNT_REQUIRED", "demo_lock": demo_details},
                )
                return context

        if decision.status in (ExecutionDecisionStatus.DRY_RUN,):
            dry_request = {}
            try:
                dry_request = self.order_executor.build_market_order_request(signal=signal, risk_plan=risk_plan)
            except Exception:
                dry_request = {
                    "symbol": signal.symbol,
                    "volume_lot": risk_plan.lot_size,
                    "entry_price": signal.entry_price,
                    "sl": risk_plan.stop_loss,
                    "tp": risk_plan.take_profit,
                }

            created = self.execution_repository.create_execution_order(
                signal_id=signal_id,
                execution_decision_id=decision_id,
                symbol_id=symbol_id,
                side=signal.direction.value,
                order_type="MARKET",
                volume_lot=risk_plan.lot_size,
                requested_price=signal.entry_price,
                stop_loss=risk_plan.stop_loss,
                take_profit=risk_plan.take_profit,
                deviation=int(self.settings.order_deviation),
                status=OrderExecutionStatus.DRY_RUN.value,
                broker_response={
                    "request": dry_request,
                    "response": {"message": "DRY_RUN decision from execution gate"},
                },
                executed_at=self._now(),
            )
            self.execution_repository.session.commit()
            context.order_result = OrderResult(
                status=OrderExecutionStatus.DRY_RUN,
                dry_run=True,
                submitted_at=self._now(),
                request_payload={"signal_id": str(signal_id)},
                response_payload={"execution_order_id": str(created.id)},
            )
            return context

        if decision.status != ExecutionDecisionStatus.APPROVE_AUTO:
            context.reject("ORDER_EXECUTION_FAILED", {"message": f"invalid decision for execution: {decision.status.value}"})
            return context

        if bool(self.settings.dry_run):
            context.reject("ORDER_EXECUTION_FAILED", {"message": "settings.DRY_RUN=true while decision APPROVE_AUTO"})
            return context

        request: dict | None = None
        pending = None
        try:
            request = self.order_executor.build_market_order_request(signal=signal, risk_plan=risk_plan)
            check_result = self.order_executor.order_check(request)
            check_retcode = int((check_result or {}).get("retcode", -1))
            if check_retcode <= 0:
                self.execution_repository.create_execution_order(
                    signal_id=signal_id,
                    execution_decision_id=decision_id,
                    symbol_id=symbol_id,
                    side=signal.direction.value,
                    order_type="MARKET",
                    volume_lot=risk_plan.lot_size,
                    requested_price=signal.entry_price,
                    stop_loss=risk_plan.stop_loss,
                    take_profit=risk_plan.take_profit,
                    deviation=int(self.settings.order_deviation),
                    status=OrderExecutionStatus.REJECTED.value,
                    broker_response={"request": request, "response": check_result or {}},
                    error_message="order_check failed",
                    executed_at=self._now(),
                )
                self.execution_repository.session.commit()
                context.reject("ORDER_EXECUTION_FAILED", {"message": "order_check failed", "result": check_result})
                return context

            pending = self.execution_repository.create_execution_order(
                signal_id=signal_id,
                execution_decision_id=decision_id,
                symbol_id=symbol_id,
                side=signal.direction.value,
                order_type="MARKET",
                volume_lot=risk_plan.lot_size,
                requested_price=signal.entry_price,
                stop_loss=risk_plan.stop_loss,
                take_profit=risk_plan.take_profit,
                deviation=int(self.settings.order_deviation),
                status=OrderExecutionStatus.SUBMITTED.value,
                broker_response={"request": request, "response": {"order_check": check_result}},
                executed_at=self._now(),
            )
            self.execution_repository.session.commit()

            result = self.order_executor.send_market_order(signal=signal, risk_plan=risk_plan, decision=decision)
            updated = self.execution_repository.update_execution_order_result(
                order_id=pending.id,
                status=result.status.value,
                mt5_order_ticket=result.order_ticket,
                broker_response={"request": request, "response": result.response_payload},
                error_message=result.error_message,
                executed_at=result.submitted_at or self._now(),
            )
            self.execution_repository.session.commit()

            context.order_result = result

            if result.status not in (OrderExecutionStatus.FILLED, OrderExecutionStatus.SUBMITTED):
                context.reject(
                    "ORDER_EXECUTION_FAILED",
                    {
                        "message": result.error_message or "order execution rejected",
                        "execution_order_id": str(updated.id) if updated else None,
                    },
                )
            return context
        except Exception as exc:
            self.execution_repository.session.rollback()
            fail_order = self.execution_repository.create_execution_order(
                signal_id=signal_id,
                execution_decision_id=decision_id,
                symbol_id=symbol_id,
                side=signal.direction.value,
                order_type="MARKET",
                volume_lot=risk_plan.lot_size,
                requested_price=signal.entry_price,
                stop_loss=risk_plan.stop_loss,
                take_profit=risk_plan.take_profit,
                deviation=int(self.settings.order_deviation),
                status=OrderExecutionStatus.ERROR.value,
                broker_response={"request": request or {}, "response": {}},
                error_message=str(exc),
                executed_at=self._now(),
            )
            self.execution_repository.session.commit()

            context.order_result = OrderResult(
                status=OrderExecutionStatus.ERROR,
                dry_run=False,
                submitted_at=self._now(),
                error_message=str(exc),
                request_payload=request or {},
                response_payload={},
            )
            context.reject(
                "ORDER_EXECUTION_FAILED",
                {"message": str(exc), "execution_order_id": str(fail_order.id)},
            )
            return context
