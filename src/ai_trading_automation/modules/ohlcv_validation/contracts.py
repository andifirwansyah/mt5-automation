"""Contracts for OHLCV validation module."""

from dataclasses import dataclass

from ai_trading_automation.modules.market_data.models import OHLCVFrame


@dataclass(slots=True)
class OHLCVValidationRequest:
    """Input contract for OHLCV validation workflow."""

    raw_frame: OHLCVFrame
