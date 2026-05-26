"""Errors for position monitor module."""


class PositionMonitorError(Exception):
    """Base error for position_monitor module."""


class PositionMonitorInputError(PositionMonitorError):
    """Raised when position monitor receives invalid inputs."""
