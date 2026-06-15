"""Runtime bridge to dispatch WhatsApp notifications from real trading events."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from src.config.settings import AppSettings
from src.domain.enums import ExecutionDecisionStatus, OrderExecutionStatus
from src.infrastructure.notification import GroqNarratorClient, NotificationEventType, WwebClient
from src.pipeline.trading_context import TradingContext
from src.repositories.notification_repository import NotificationRepository
from src.services.notification_message_builder import NotificationMessageBuilder
from src.services.notification_narrator_service import NotificationNarratorService
from src.services.whatsapp_dispatch_service import WhatsappDispatchService


class NotificationRuntimeService:
    """Non-fatal runtime notification dispatcher for real trading events."""

    def __init__(self, session_factory: Callable[[], Session], settings: AppSettings) -> None:
        self.session_factory = session_factory
        self.settings = settings

    def process_trading_context(self, context: TradingContext) -> None:
        session = self.session_factory()
        try:
            service = self._build_dispatch_service(session)
            signal_payload, signal_source_key = self._build_signal_ready_payload(context)
            if signal_payload is not None and signal_source_key is not None:
                service.dispatch_event(
                    event_type=NotificationEventType.SIGNAL_READY,
                    payload=signal_payload,
                    source_key=signal_source_key,
                )

            trade_payload, trade_source_key = self._build_trade_opened_payload(context)
            if trade_payload is not None and trade_source_key is not None:
                service.dispatch_event(
                    event_type=NotificationEventType.TRADE_OPENED,
                    payload=trade_payload,
                    source_key=trade_source_key,
                )
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Notification runtime service failed to process trading context")
        finally:
            session.close()

    def process_closed_positions(self, positions: list[Any]) -> None:
        if not positions:
            return
        session = self.session_factory()
        try:
            service = self._build_dispatch_service(session)
            for position in positions:
                payload, source_key = self._build_trade_closed_payload(position)
                service.dispatch_event(
                    event_type=NotificationEventType.TRADE_CLOSED,
                    payload=payload,
                    source_key=source_key,
                )
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Notification runtime service failed to process closed positions")
        finally:
            session.close()

    def _build_dispatch_service(self, session: Session) -> WhatsappDispatchService:
        narrator_client = None
        if self.settings.notification_ai_enabled and self.settings.groq_secret_key.strip():
            narrator_client = GroqNarratorClient(
                base_url=self.settings.groq_base_url,
                api_key=self.settings.groq_secret_key,
                model=self.settings.groq_model,
                timeout_seconds=self.settings.groq_request_timeout_seconds,
            )
        return WhatsappDispatchService(
            repository=NotificationRepository(session),
            wweb_client=WwebClient(
                base_url=self.settings.wweb_base_url,
                api_key=self.settings.wweb_api_key,
                timeout_seconds=self.settings.wweb_request_timeout_seconds,
            ),
            message_builder=NotificationMessageBuilder(),
            narrator_service=NotificationNarratorService(
                client=narrator_client,
                enabled=self.settings.notification_ai_enabled and bool(self.settings.groq_secret_key.strip()),
                max_sentences=self.settings.notification_ai_max_sentences,
            ),
            retry_enabled=self.settings.notification_retry_enabled,
            retry_max_attempts=self.settings.notification_retry_max_attempts,
            retry_batch_limit=self.settings.notification_retry_batch_limit,
            retry_backoff_base_seconds=self.settings.notification_retry_backoff_base_seconds,
            retry_backoff_multiplier=self.settings.notification_retry_backoff_multiplier,
            retry_backoff_max_seconds=self.settings.notification_retry_backoff_max_seconds,
        )

    def _build_signal_ready_payload(self, context: TradingContext) -> tuple[dict[str, Any] | None, str | None]:
        signal = context.signal_contract
        decision = context.execution_decision
        if signal is None or decision is None:
            return None, None
        if decision.status not in (
            ExecutionDecisionStatus.APPROVE_AUTO,
            ExecutionDecisionStatus.DRY_RUN,
            ExecutionDecisionStatus.REQUIRE_MANUAL_APPROVAL,
        ):
            return None, None
        signal_id = str(signal.metadata.get("signal_id") or "").strip()
        if not signal_id:
            return None, None
        payload = {
            "symbol": signal.symbol,
            "direction": signal.direction.value,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "strategy": signal.strategy_code,
            "mode": "DRY_RUN" if decision.status == ExecutionDecisionStatus.DRY_RUN else "AUTO",
            "signal_time": signal.generated_at,
            "trace_id": str(context.trace_id),
            "summary": signal.metadata.get("reason"),
        }
        return payload, f"signal_ready:{signal_id}"

    def _build_trade_opened_payload(self, context: TradingContext) -> tuple[dict[str, Any] | None, str | None]:
        signal = context.signal_contract
        order_result = context.order_result
        risk_plan = context.risk_plan
        if signal is None or order_result is None or risk_plan is None:
            return None, None
        if order_result.status not in (OrderExecutionStatus.DRY_RUN, OrderExecutionStatus.SUBMITTED, OrderExecutionStatus.FILLED):
            return None, None
        signal_id = str(signal.metadata.get("signal_id") or "").strip()
        execution_order_id = str((order_result.response_payload or {}).get("execution_order_id") or "").strip()
        source_key = f"trade_opened:{execution_order_id or signal_id}:{order_result.status.value}"
        payload = {
            "symbol": signal.symbol,
            "side": signal.direction.value,
            "lot_size": risk_plan.lot_size,
            "entry_price": signal.entry_price,
            "stop_loss": risk_plan.stop_loss,
            "take_profit": risk_plan.take_profit,
            "strategy": signal.strategy_code,
            "mode": "DRY_RUN" if order_result.dry_run else "LIVE",
            "opened_at": order_result.submitted_at or datetime.now(timezone.utc),
            "trace_id": str(context.trace_id),
            "summary": signal.metadata.get("reason"),
        }
        return payload, source_key

    def _build_trade_closed_payload(self, position: Any) -> tuple[dict[str, Any], str]:
        details = getattr(position, "details", {}) or {}
        symbol = str(details.get("symbol") or details.get("symbol_name") or "UNKNOWN")
        profit = float(getattr(position, "profit", 0.0) or 0.0)
        result = "WIN" if profit > 0 else "LOSS" if profit < 0 else "BREAKEVEN"
        opened_at = getattr(position, "opened_at", None)
        closed_at = getattr(position, "closed_at", None)
        duration = None
        if opened_at is not None and closed_at is not None:
            seconds = max(0, int((closed_at - opened_at).total_seconds()))
            duration = f"{seconds // 60}m"
        payload = {
            "symbol": symbol,
            "side": getattr(position, "side", "UNKNOWN"),
            "entry_price": float(getattr(position, "entry_price", 0.0) or 0.0),
            "close_price": float(getattr(position, "close_price", 0.0) or 0.0),
            "pnl": profit,
            "result": result,
            "exit_reason": "POSITION_CLOSED",
            "duration": duration,
            "closed_at": closed_at,
            "summary": details.get("close_reason") or "Position closed by lifecycle sync",
        }
        closed_at_key = closed_at.isoformat() if isinstance(closed_at, datetime) else "unknown"
        return payload, f"trade_closed:{getattr(position, 'id', 'unknown')}:{closed_at_key}"
