"""Errors for strategy engine shell module."""


class StrategyEngineError(Exception):
    """Base error for strategy_engine module."""


class StrategyEngineInputError(StrategyEngineError):
    """Raised when strategy engine input is invalid."""


class StrategyNotRegisteredError(StrategyEngineError):
    """Raised when a strategy key does not exist in registry."""
