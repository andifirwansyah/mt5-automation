"""Errors for market regime detection module."""


class MarketRegimeError(Exception):
    """Base error for market_regime module."""


class MarketRegimeInputError(MarketRegimeError):
    """Raised when regime detection receives invalid input."""
