"""Errors for trade journal module."""


class TradeJournalError(Exception):
    """Base error for trade_journal module."""


class TradeJournalInputError(TradeJournalError):
    """Raised when journal request payload is invalid."""
