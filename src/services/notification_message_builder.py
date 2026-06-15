"""Notification message builder for deterministic facts and rendered text."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from src.infrastructure.notification.models import (
    NotificationEventType,
    NotificationFact,
    NotificationMessagePayload,
    NotificationNarrativeResult,
    RenderedNotificationMessage,
)


class NotificationMessageBuilder:
    """Build deterministic notification facts before channel delivery."""

    def build_payload(
        self,
        event_type: NotificationEventType,
        payload: Mapping[str, Any],
    ) -> NotificationMessagePayload:
        """Build event-specific message payload from source-of-truth data."""

        handlers = {
            NotificationEventType.SIGNAL_READY: self._build_signal_ready,
            NotificationEventType.TRADE_OPENED: self._build_trade_opened,
            NotificationEventType.TRADE_CLOSED: self._build_trade_closed,
            NotificationEventType.DAILY_SUMMARY: self._build_daily_summary,
        }
        return handlers[event_type](payload)

    def render_message(
        self,
        payload: NotificationMessagePayload,
        narrative: NotificationNarrativeResult,
    ) -> RenderedNotificationMessage:
        """Combine deterministic facts with narrative into final text."""

        fact_lines = [f"- {fact.label}: {fact.value}" for fact in payload.facts]
        sections = [payload.title]
        if fact_lines:
            sections.append("\n".join(fact_lines))
        if narrative.narrative:
            sections.append(narrative.narrative.strip())
        if payload.trace_id:
            sections.append(f"Trace ID: {payload.trace_id}")

        return RenderedNotificationMessage(
            payload=payload,
            narrative=narrative,
            text="\n\n".join(section for section in sections if section.strip()),
        )

    def _build_signal_ready(self, payload: Mapping[str, Any]) -> NotificationMessagePayload:
        facts = (
            NotificationFact("Symbol", self._stringify(payload.get("symbol"))),
            NotificationFact("Direction", self._stringify(payload.get("direction"))),
            NotificationFact("Entry", self._format_price(payload.get("entry_price"))),
            NotificationFact("Stop Loss", self._format_price(payload.get("stop_loss"))),
            NotificationFact("Take Profit", self._format_price(payload.get("take_profit"))),
            NotificationFact("Strategy", self._stringify(payload.get("strategy"))),
            NotificationFact("Mode", self._stringify(payload.get("mode", "DRY_RUN"))),
            NotificationFact("Signal Time", self._format_time(payload.get("signal_time"))),
        )
        return NotificationMessagePayload(
            event_type=NotificationEventType.SIGNAL_READY,
            title="📡 Signal Ready",
            facts=self._compact_facts(facts),
            summary=self._stringify(payload.get("summary"), default=None),
            trace_id=self._stringify(payload.get("trace_id"), default=None),
            metadata=dict(payload),
        )

    def _build_trade_opened(self, payload: Mapping[str, Any]) -> NotificationMessagePayload:
        facts = (
            NotificationFact("Symbol", self._stringify(payload.get("symbol"))),
            NotificationFact("Side", self._stringify(payload.get("side", payload.get("direction")))),
            NotificationFact("Lot", self._format_number(payload.get("lot_size"))),
            NotificationFact("Entry", self._format_price(payload.get("entry_price"))),
            NotificationFact("Stop Loss", self._format_price(payload.get("stop_loss"))),
            NotificationFact("Take Profit", self._format_price(payload.get("take_profit"))),
            NotificationFact("Strategy", self._stringify(payload.get("strategy"))),
            NotificationFact("Mode", self._stringify(payload.get("mode", "DRY_RUN"))),
            NotificationFact("Opened At", self._format_time(payload.get("opened_at"))),
        )
        return NotificationMessagePayload(
            event_type=NotificationEventType.TRADE_OPENED,
            title="✅ Trade Opened",
            facts=self._compact_facts(facts),
            summary=self._stringify(payload.get("summary"), default=None),
            trace_id=self._stringify(payload.get("trace_id"), default=None),
            metadata=dict(payload),
        )

    def _build_trade_closed(self, payload: Mapping[str, Any]) -> NotificationMessagePayload:
        facts = (
            NotificationFact("Symbol", self._stringify(payload.get("symbol"))),
            NotificationFact("Side", self._stringify(payload.get("side", payload.get("direction")))),
            NotificationFact("Entry", self._format_price(payload.get("entry_price"))),
            NotificationFact("Close", self._format_price(payload.get("close_price"))),
            NotificationFact("PnL", self._format_signed_number(payload.get("pnl"))),
            NotificationFact("Result", self._stringify(payload.get("result"))),
            NotificationFact("Exit Reason", self._stringify(payload.get("exit_reason"))),
            NotificationFact("Duration", self._stringify(payload.get("duration"))),
            NotificationFact("Closed At", self._format_time(payload.get("closed_at"))),
        )
        return NotificationMessagePayload(
            event_type=NotificationEventType.TRADE_CLOSED,
            title="📘 Trade Closed",
            facts=self._compact_facts(facts),
            summary=self._stringify(payload.get("summary"), default=None),
            trace_id=self._stringify(payload.get("trace_id"), default=None),
            metadata=dict(payload),
        )

    def _build_daily_summary(self, payload: Mapping[str, Any]) -> NotificationMessagePayload:
        facts = (
            NotificationFact("Date", self._stringify(payload.get("date"))),
            NotificationFact("Mode", self._stringify(payload.get("mode", "DRY_RUN"))),
            NotificationFact("Closed Trades", self._format_number(payload.get("closed_trades"))),
            NotificationFact("Wins", self._format_number(payload.get("wins"))),
            NotificationFact("Losses", self._format_number(payload.get("losses"))),
            NotificationFact("Win Rate", self._format_percentage(payload.get("win_rate"))),
            NotificationFact("Net PnL", self._format_signed_number(payload.get("net_pnl"))),
            NotificationFact("Open Positions", self._format_number(payload.get("open_positions"))),
        )
        return NotificationMessagePayload(
            event_type=NotificationEventType.DAILY_SUMMARY,
            title="📊 Daily Trading Summary",
            facts=self._compact_facts(facts),
            summary=self._stringify(payload.get("summary"), default=None),
            trace_id=self._stringify(payload.get("trace_id"), default=None),
            metadata=dict(payload),
        )

    @staticmethod
    def _compact_facts(facts: tuple[NotificationFact, ...]) -> tuple[NotificationFact, ...]:
        return tuple(fact for fact in facts if fact.value not in {"", "-"})

    @staticmethod
    def _stringify(value: Any, default: str | None = "-") -> str | None:
        if value is None:
            return default
        text = str(value).strip()
        if not text:
            return default
        return text

    @staticmethod
    def _format_time(value: Any) -> str:
        if value is None:
            return "-"
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    def _format_price(self, value: Any) -> str:
        number = self._to_decimal(value)
        if number is None:
            return "-"
        return f"{number:.2f}"

    def _format_number(self, value: Any) -> str:
        number = self._to_decimal(value)
        if number is None:
            return "-"
        normalized = number.normalize()
        normalized_text = format(normalized, "f")
        if "." not in normalized_text:
            return normalized_text
        return normalized_text.rstrip("0").rstrip(".")

    def _format_signed_number(self, value: Any) -> str:
        number = self._to_decimal(value)
        if number is None:
            return "-"
        prefix = "+" if number > 0 else ""
        return f"{prefix}{number:.2f}"

    def _format_percentage(self, value: Any) -> str:
        number = self._to_decimal(value)
        if number is None:
            return "-"
        if number <= 1:
            number *= Decimal("100")
        return f"{number:.2f}%"
