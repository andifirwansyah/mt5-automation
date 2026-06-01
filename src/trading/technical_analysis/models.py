"""Domain models for technical analysis evidence output."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

TechnicalBias = Literal["buy", "sell", "neutral"]


@dataclass(slots=True)
class SwingPoint:
    """Single swing point reference from candle structure."""

    index: int
    price: float
    kind: Literal["high", "low"]
    candle_time: datetime | None = None


@dataclass(slots=True)
class FVG:
    """Fair Value Gap representation."""

    type: Literal["bullish_fvg", "bearish_fvg"]
    low: float
    high: float
    midpoint: float
    status: Literal["open", "partial", "filled"]
    age_bars: int
    filled_percent: float
    confidence: float
    timeframe: str | None = None
    created_index: int | None = None


@dataclass(slots=True)
class DoubleTopPattern:
    """Double top pattern structure."""

    left_peak: SwingPoint
    right_peak: SwingPoint
    neckline: float
    is_neckline_broken: bool
    confidence: float
    status: str = "detected"
    warnings: list[str] = field(default_factory=list)
    rejection_reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DoubleBottomPattern:
    """Double bottom pattern structure."""

    left_bottom: SwingPoint
    right_bottom: SwingPoint
    neckline: float
    is_neckline_broken: bool
    confidence: float
    status: str = "detected"
    warnings: list[str] = field(default_factory=list)
    rejection_reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PatternEvidence:
    """Normalized evidence contract for any technical pattern."""

    pattern_type: str
    signal: Literal["buy", "sell", "neutral", "conflict"]
    confidence: float
    fvgs: list[FVG] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TechnicalAnalysisResult:
    """Technical analysis result carried inside TradingContext."""

    symbol: str
    timeframe: str
    bias: TechnicalBias
    technical_score: float
    buy_score: float = 0.0
    sell_score: float = 0.0
    pattern_evidence: list[PatternEvidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    strategy_hints: list[str] = field(default_factory=list)
    conflict_flags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    analyzed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
