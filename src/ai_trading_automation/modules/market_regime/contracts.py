"""Contracts for market regime detection module."""

from dataclasses import dataclass, field

from ai_trading_automation.modules.ohlcv_validation.models import ValidatedOHLCVFrame


@dataclass(slots=True)
class MarketRegimeThresholds:
    """Configurable thresholds to reduce hardcoded regime fitting."""

    min_rows: int = 30
    trend_strength_min: float = 0.015
    trend_direction_consistency_min: float = 0.60
    range_width_max: float = 0.02
    high_volatility_min: float = 0.015
    low_volatility_max: float = 0.004
    choppy_change_ratio_min: float = 0.55


@dataclass(slots=True)
class MarketRegimeRequest:
    """Input contract for market regime detection."""

    primary_frame: ValidatedOHLCVFrame
    context_frames: dict[str, ValidatedOHLCVFrame] = field(default_factory=dict)
    thresholds: MarketRegimeThresholds = field(default_factory=MarketRegimeThresholds)
