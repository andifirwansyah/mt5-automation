"""Errors for strategy selector module."""


class StrategySelectorError(Exception):
    """Base error for strategy_selector module."""


class StrategySelectorInputError(StrategySelectorError):
    """Raised when strategy selector input is invalid."""
