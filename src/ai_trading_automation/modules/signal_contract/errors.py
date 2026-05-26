"""Errors for signal contract module."""


class SignalContractError(Exception):
    """Base error for signal_contract module."""


class SignalContractBuildError(SignalContractError):
    """Raised when raw candidate cannot be converted to valid signal contract."""
