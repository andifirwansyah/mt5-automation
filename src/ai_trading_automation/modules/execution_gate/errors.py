"""Errors for execution gate module."""


class ExecutionGateError(Exception):
    """Base error for execution_gate module."""


class ExecutionGateInputError(ExecutionGateError):
    """Raised when execution gate receives invalid input contract."""
