"""Domain models for market structure context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


StructureTrend = Literal["BULLISH", "BEARISH", "RANGING", "UNCLEAR"]


@dataclass(slots=True)
class StructurePoint:
    """Reference swing point used to build support/resistance context."""

    price: float
    kind: Literal["support", "resistance"]
    index: int | None = None
    candle_time: datetime | None = None


@dataclass(slots=True)
class PriceZone:
    """Support/resistance zone around a structure point."""

    kind: Literal["support", "resistance"]
    center: float
    low: float
    high: float
    source: str = "swing"

    def contains(self, price: float) -> bool:
        return self.low <= price <= self.high


@dataclass(slots=True)
class MarketStructureResult:
    """Market location contract consumed by strategy selector and signal validator."""

    symbol: str
    timeframe: str
    trend_structure: StructureTrend
    current_price: float
    atr: float
    nearest_support: float | None = None
    nearest_resistance: float | None = None
    distance_to_support_points: float | None = None
    distance_to_resistance_points: float | None = None
    is_near_support: bool = False
    is_near_resistance: bool = False
    valid_buy_zone: bool = False
    valid_sell_zone: bool = False
    break_of_structure: bool = False
    liquidity_sweep_detected: bool = False
    support_zones: list[PriceZone] = field(default_factory=list)
    resistance_zones: list[PriceZone] = field(default_factory=list)
    swing_points: list[StructurePoint] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    analyzed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_summary(self) -> dict[str, Any]:
        """Return JSON-safe summary for audit/details payloads."""

        return {
            "trend_structure": self.trend_structure,
            "current_price": self.current_price,
            "atr": self.atr,
            "nearest_support": self.nearest_support,
            "nearest_resistance": self.nearest_resistance,
            "distance_to_support_points": self.distance_to_support_points,
            "distance_to_resistance_points": self.distance_to_resistance_points,
            "is_near_support": self.is_near_support,
            "is_near_resistance": self.is_near_resistance,
            "valid_buy_zone": self.valid_buy_zone,
            "valid_sell_zone": self.valid_sell_zone,
            "break_of_structure": self.break_of_structure,
            "liquidity_sweep_detected": self.liquidity_sweep_detected,
            "notes": list(self.notes),
        }
