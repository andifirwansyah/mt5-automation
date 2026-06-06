"""Configuration for Market Structure Engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class MarketStructureConfig:
    """Runtime knobs for support/resistance location detection."""

    enabled: bool = True
    min_candles_required: int = 30
    max_candles_lookback: int = 300
    swing_left_bars: int = 3
    swing_right_bars: int = 3
    swing_min_distance_atr: float = 0.15
    zone_tolerance_atr: float = 0.45
    danger_zone_atr: float = 0.55
    minimum_room_to_zone_atr: float = 0.80
    fallback_atr: float = 1.0

    @classmethod
    def from_settings(cls, settings: Any) -> "MarketStructureConfig":
        """Build config from runtime settings/proxy while preserving safe defaults."""

        return cls(
            min_candles_required=int(getattr(settings, "market_structure_min_candles_required", cls.min_candles_required)),
            zone_tolerance_atr=float(getattr(settings, "market_structure_zone_tolerance_atr", cls.zone_tolerance_atr)),
            danger_zone_atr=float(getattr(settings, "market_structure_danger_zone_atr", cls.danger_zone_atr)),
            minimum_room_to_zone_atr=float(getattr(settings, "market_structure_soft_min_room_atr", cls.minimum_room_to_zone_atr)),
        )
