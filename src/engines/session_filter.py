"""Market session filter engine."""

from __future__ import annotations

from datetime import time, timezone
from typing import Any

from src.config.settings import AppSettings, get_settings
from src.domain.enums import ValidationStatus
from src.domain.models.validation_result import ValidationResult
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext


class SessionFilter(PipelineStep):
    """Filter trading by UTC market session and rollover safety window."""

    @property
    def name(self) -> str:
        return "SessionFilter"

    def __init__(self, settings: AppSettings | Any | None = None) -> None:
        self.settings = settings or get_settings()

    @staticmethod
    def _session_name(t: time) -> str:
        if time(0, 0) <= t < time(7, 0):
            return "ASIA"
        if time(7, 0) <= t < time(13, 0):
            return "LONDON"
        if time(13, 0) <= t < time(21, 0):
            return "NEW_YORK"
        return "ROLLOVER"

    @staticmethod
    def _parse_sessions(raw: str) -> set[str]:
        return {item.strip().upper() for item in str(raw).split(",") if item.strip()}

    def run(self, context: TradingContext) -> TradingContext:
        candle_time = context.candle_time if context.candle_time.tzinfo else context.candle_time.replace(tzinfo=timezone.utc)
        utc_time = candle_time.astimezone(timezone.utc).time()
        session_name = self._session_name(utc_time)
        allowed_sessions = self._parse_sessions(getattr(self.settings, "session_filter_allowed_sessions", "ASIA,LONDON,NEW_YORK"))
        block_rollover = bool(getattr(self.settings, "session_filter_block_rollover", True))

        details = {
            "session": session_name,
            "utc_time": utc_time.isoformat(),
            "allowed_sessions": sorted(allowed_sessions),
            "block_rollover": block_rollover,
        }

        if session_name == "ROLLOVER" and block_rollover:
            context.session_filter_result = ValidationResult(
                status=ValidationStatus.REJECTED,
                reason="SESSION_ROLLOVER_BLOCKED",
                validator_name=self.name,
                details={**details, "message": "Rollover session blocked"},
            )
            context.reject("SESSION_ROLLOVER_BLOCKED", context.session_filter_result.details)
            return context

        if allowed_sessions and session_name not in allowed_sessions:
            context.session_filter_result = ValidationResult(
                status=ValidationStatus.REJECTED,
                reason="SESSION_NOT_ALLOWED",
                validator_name=self.name,
                details={**details, "message": "Current session is not allowed"},
            )
            context.reject("SESSION_NOT_ALLOWED", context.session_filter_result.details)
            return context

        context.session_filter_result = ValidationResult(
            status=ValidationStatus.PASSED,
            validator_name=self.name,
            details={**details, "message": "Session allowed"},
        )
        return context
