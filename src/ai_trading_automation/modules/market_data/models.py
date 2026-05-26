"""Models for market data module."""

from dataclasses import dataclass

import pandas as pd


@dataclass(slots=True)
class OHLCVFrame:
    """Raw OHLCV frame after basic column normalization."""

    symbol: str
    timeframe: str
    frame: pd.DataFrame
