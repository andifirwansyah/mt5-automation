"""Errors for OHLCV validation module."""


class OHLCVValidationError(Exception):
    """Base error for OHLCV validation module."""


class OHLCVValidationInputError(OHLCVValidationError):
    """Raised when input contract is invalid or missing."""
