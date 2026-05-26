"""Models for OHLCV validation module."""

from dataclasses import dataclass
from datetime import datetime

import pandas as pd


@dataclass(slots=True)
class OHLCVValidationResult:
    """Validation result for raw OHLCV frame."""

    is_valid: bool
    errors: list[str]
    warnings: list[str]
    row_count: int
    start_time: datetime | None
    end_time: datetime | None
    timeframe: str
    symbol: str


@dataclass(slots=True)
class ValidatedOHLCVFrame:
    """Validated OHLCV frame returned when data passes checks."""

    symbol: str
    timeframe: str
    frame: pd.DataFrame
