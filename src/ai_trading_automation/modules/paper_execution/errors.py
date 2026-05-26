"""Errors for paper execution module."""


class PaperExecutionError(Exception):
    """Base error for paper_execution module."""


class PaperExecutionInputError(PaperExecutionError):
    """Raised when input contract is invalid."""


class PaperExecutionBlockedError(PaperExecutionError):
    """Raised when decision is not eligible for paper order creation."""
