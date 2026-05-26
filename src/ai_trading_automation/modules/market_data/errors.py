"""Errors for market data loading workflow."""


class MarketDataError(Exception):
    """Base error for market_data module."""


class UnsupportedTimeframeError(MarketDataError):
    """Raised when the timeframe is outside the allowed list."""


class DatasetFileNotFoundError(MarketDataError):
    """Raised when timeframe directory or dataset file is missing."""


class DatasetFormatError(MarketDataError):
    """Raised when dataset file exists but cannot be parsed properly."""
