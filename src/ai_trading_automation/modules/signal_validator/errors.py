"""Errors for signal validator module."""


class SignalValidatorError(Exception):
    """Base error for signal_validator module."""


class SignalValidatorInputError(SignalValidatorError):
    """Raised when signal validator receives invalid input contract."""
