"""Domain enums used across trading pipeline internal models."""

from __future__ import annotations

from enum import StrEnum


class MarketRegimeType(StrEnum):
    TRENDING_BULLISH = "TRENDING_BULLISH"
    TRENDING_BEARISH = "TRENDING_BEARISH"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    CHOPPY = "CHOPPY"
    UNKNOWN = "UNKNOWN"


class SignalDirection(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    FLAT = "FLAT"


class ValidationStatus(StrEnum):
    PASSED = "PASSED"
    REJECTED = "REJECTED"


class ExecutionDecisionStatus(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    APPROVE_AUTO = "APPROVE_AUTO"
    DRY_RUN = "DRY_RUN"
    REQUIRE_MANUAL_APPROVAL = "REQUIRE_MANUAL_APPROVAL"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"


class OrderExecutionStatus(StrEnum):
    CREATED = "CREATED"
    DRY_RUN = "DRY_RUN"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    ERROR = "ERROR"
