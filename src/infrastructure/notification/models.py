"""Notification contracts for channel delivery and message composition."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NotificationEventType(str, Enum):
    """Supported notification events for current rollout."""

    SIGNAL_READY = "SIGNAL_READY"
    TRADE_OPENED = "TRADE_OPENED"
    TRADE_CLOSED = "TRADE_CLOSED"
    DAILY_SUMMARY = "DAILY_SUMMARY"


@dataclass(frozen=True, slots=True)
class NotificationFact:
    """Single human-readable fact line for notifications."""

    label: str
    value: str


@dataclass(frozen=True, slots=True)
class NotificationMessagePayload:
    """Structured facts that stay deterministic before narration."""

    event_type: NotificationEventType
    title: str
    facts: tuple[NotificationFact, ...]
    summary: str | None = None
    trace_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NotificationNarrativeResult:
    """Result of AI or fallback narration."""

    narrative: str
    used_fallback: bool
    provider: str


@dataclass(frozen=True, slots=True)
class RenderedNotificationMessage:
    """Final rendered channel-ready text message."""

    payload: NotificationMessagePayload
    narrative: NotificationNarrativeResult
    text: str
