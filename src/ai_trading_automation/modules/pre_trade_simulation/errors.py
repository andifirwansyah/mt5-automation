"""Errors for pre-trade simulation module."""


class PreTradeSimulationError(Exception):
    """Base error for pre_trade_simulation module."""


class PreTradeSimulationInputError(PreTradeSimulationError):
    """Raised when simulation input contract is invalid."""
