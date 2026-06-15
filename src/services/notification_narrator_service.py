"""Narration service that enriches notification facts with constrained AI text."""

from __future__ import annotations

from typing import Protocol

from src.infrastructure.notification.models import (
    NotificationEventType,
    NotificationMessagePayload,
    NotificationNarrativeResult,
)


class NarrationClient(Protocol):
    """Protocol for external narration providers."""

    def generate_narrative(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 180,
    ) -> str:
        ...


class NotificationNarratorService:
    """Produce human-readable narrative with strict fallback behavior."""

    def __init__(
        self,
        *,
        client: NarrationClient | None,
        enabled: bool = True,
        max_sentences: int = 3,
    ) -> None:
        self.client = client
        self.enabled = enabled
        self.max_sentences = max(1, max_sentences)

    def narrate(self, payload: NotificationMessagePayload) -> NotificationNarrativeResult:
        """Return AI narrative when available, otherwise deterministic fallback."""

        fallback = self._fallback_text(payload)
        if not self.enabled or self.client is None:
            return NotificationNarrativeResult(
                narrative=fallback,
                used_fallback=True,
                provider="fallback_template",
            )

        try:
            narrative = self.client.generate_narrative(
                system_prompt=self._build_system_prompt(),
                user_prompt=self._build_user_prompt(payload),
            ).strip()
        except Exception:
            return NotificationNarrativeResult(
                narrative=fallback,
                used_fallback=True,
                provider="fallback_template",
            )

        return NotificationNarrativeResult(
            narrative=narrative or fallback,
            used_fallback=not bool(narrative),
            provider="groq" if narrative else "fallback_template",
        )

    def _build_system_prompt(self) -> str:
        return (
            "You are a trading notification narrator. "
            "Write concise Bahasa Indonesia, human-readable, max "
            f"{self.max_sentences} sentences. "
            "Do not add facts outside input. Do not change any numbers. "
            "Do not promise profit. Do not give financial advice. "
            "Only summarize the provided facts in a calm operational tone."
        )

    def _build_user_prompt(self, payload: NotificationMessagePayload) -> str:
        facts = "\n".join(f"- {fact.label}: {fact.value}" for fact in payload.facts)
        summary = f"\nSummary hint: {payload.summary}" if payload.summary else ""
        trace = f"\nTrace ID: {payload.trace_id}" if payload.trace_id else ""
        return f"Event: {payload.event_type.value}\nTitle: {payload.title}\nFacts:\n{facts}{summary}{trace}"

    def _fallback_text(self, payload: NotificationMessagePayload) -> str:
        metadata = payload.metadata
        if payload.event_type == NotificationEventType.SIGNAL_READY:
            symbol = metadata.get("symbol", "instrument")
            direction = metadata.get("direction", "WAIT")
            return f"Sinyal {direction} untuk {symbol} berhasil dirangkum dari fakta trading yang tersedia saat ini."
        if payload.event_type == NotificationEventType.TRADE_OPENED:
            symbol = metadata.get("symbol", "instrument")
            side = metadata.get("side", metadata.get("direction", "POSITION"))
            return f"Posisi {side} pada {symbol} sudah tercatat berdasarkan detail entry yang tersedia di sistem."
        if payload.event_type == NotificationEventType.TRADE_CLOSED:
            symbol = metadata.get("symbol", "instrument")
            pnl = metadata.get("pnl")
            pnl_text = f" dengan hasil {pnl}" if pnl is not None else ""
            return f"Trade pada {symbol} sudah ditutup{pnl_text} berdasarkan hasil akhir yang tercatat di sistem."
        return "Ringkasan trading harian berhasil disusun dari data sistem yang tersedia hari ini."
