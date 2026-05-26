"""Errors for risk engine module."""


class RiskEngineError(Exception):
    """Base error for risk_engine module."""


class RiskEngineInputError(RiskEngineError):
    """Raised when risk request input is invalid."""


class RiskLimitExceededError(RiskEngineError):
    """Raised when risk policy limits are violated."""
