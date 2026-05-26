"""Errors for performance analyzer module."""


class PerformanceAnalyzerError(Exception):
    """Base error for performance_analyzer module."""


class PerformanceAnalyzerInputError(PerformanceAnalyzerError):
    """Raised when performance analyzer request is invalid."""
