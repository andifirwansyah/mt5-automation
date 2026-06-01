"""Configuration objects for Technical Analysis Engine."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SwingConfig:
    left_bars: int = 3
    right_bars: int = 3
    min_distance_atr: float = 0.15


@dataclass(slots=True)
class DoubleTopConfig:
    enabled: bool = True
    max_top_distance_atr: float = 0.40
    min_bars_between_tops: int = 4
    max_bars_between_tops: int = 100
    min_neckline_depth_atr: float = 0.35
    require_neckline_break: bool = False


@dataclass(slots=True)
class DoubleBottomConfig:
    enabled: bool = True
    max_bottom_distance_atr: float = 0.40
    min_bars_between_bottoms: int = 4
    max_bars_between_bottoms: int = 100
    min_neckline_depth_atr: float = 0.35
    require_neckline_break: bool = False


@dataclass(slots=True)
class NecklineBreakConfig:
    require_candle_close: bool = True
    break_buffer_atr: float = 0.08
    min_break_body_atr: float = 0.18
    allow_weak_break_as_warning: bool = True


@dataclass(slots=True)
class FVGConfig:
    enabled: bool = True
    min_fvg_size_atr: float = 0.08
    max_fvg_age_bars: int = 30
    mark_filled_when_percent_above: float = 80.0
    allow_small_fvg_as_low_confidence: bool = True
    min_confidence: float = 0.35
    prefer_impulse_body_atr: float = 0.25
    require_impulse_body: bool = False


@dataclass(slots=True)
class TechnicalAnalysisConfig:
    """Runtime knobs for technical analysis foundation layer."""

    enabled: bool = True
    min_candles_required: int = 30
    max_candles_lookback: int = 300
    enable_fvg_detection: bool = True
    enable_multi_timeframe: bool = True
    confirmation_timeframes: list[str] = field(default_factory=lambda: ["M15", "M30", "H1", "H4"])
    htf_score_weight: float = 0.35
    swing: SwingConfig = field(default_factory=SwingConfig)
    double_top: DoubleTopConfig = field(default_factory=DoubleTopConfig)
    double_bottom: DoubleBottomConfig = field(default_factory=DoubleBottomConfig)
    neckline_break: NecklineBreakConfig = field(default_factory=NecklineBreakConfig)
    fvg: FVGConfig = field(default_factory=FVGConfig)
