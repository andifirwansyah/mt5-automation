"""Scoring helpers for technical analysis evidence."""

from __future__ import annotations

from src.trading.technical_analysis.models import DoubleBottomPattern, DoubleTopPattern, FVG, PatternEvidence, TechnicalBias


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def clamp_score(value: float) -> float:
    return _clamp(value, 0.0, 1.0)


def compute_technical_score(
    bias: TechnicalBias,
    evidence: list[PatternEvidence],
    warnings: list[str],
) -> float:
    """Compute lightweight confidence score for non-blocking TA layer."""

    base = 0.5
    if bias == "buy":
        base += 0.05
    elif bias == "sell":
        base += 0.05

    evidence_boost = min(0.25, sum(max(0.0, e.confidence) for e in evidence) * 0.05)
    warning_penalty = min(0.25, len(warnings) * 0.05)
    return _clamp(base + evidence_boost - warning_penalty)


def compute_pattern_score(
    double_top: DoubleTopPattern | None,
    double_bottom: DoubleBottomPattern | None,
    fvgs: list[FVG] | None = None,
) -> float:
    """Phase-2 pattern score per requested baseline increments."""

    score = 0.0

    if double_top is not None:
        score += 0.12
        if double_top.status == "neckline_broken":
            score += 0.18

    if double_bottom is not None:
        score += 0.12
        if double_bottom.status == "neckline_broken":
            score += 0.18

    for fvg in fvgs or []:
        if fvg.status == "open":
            score += 0.08
        elif fvg.status == "partial":
            score += 0.10
        elif fvg.status == "filled":
            score += 0.02

    return clamp_score(score)


def compute_side_scores(
    double_top: DoubleTopPattern | None,
    double_bottom: DoubleBottomPattern | None,
    fvgs: list[FVG] | None = None,
) -> tuple[float, float, list[str], list[str]]:
    """Compute flexible buy/sell score with warning and conflict flags."""

    buy_score = 0.0
    sell_score = 0.0
    warnings: list[str] = []
    conflict_flags: list[str] = []

    if double_top is not None:
        sell_score += 0.12
        if double_top.status == "neckline_broken":
            sell_score += 0.18

    if double_bottom is not None:
        buy_score += 0.12
        if double_bottom.status == "neckline_broken":
            buy_score += 0.18

    for fvg in fvgs or []:
        is_buy = fvg.type == "bullish_fvg"
        inc = 0.0
        if fvg.status == "open":
            inc = 0.08
        elif fvg.status == "partial":
            inc = 0.10
        elif fvg.status == "filled":
            inc = 0.02

        if is_buy:
            buy_score += inc
        else:
            sell_score += inc

    if double_top is not None and double_top.status == "neckline_broken" and any(
        f.type == "bullish_fvg" and f.status in ("open", "partial") for f in fvgs or []
    ):
        buy_score = max(0.0, buy_score - 0.08)
        warnings.append("CONFLICT_BULLISH_FVG_VS_DOUBLE_TOP")
        conflict_flags.append("BULLISH_FVG_VS_DOUBLE_TOP")

    if double_bottom is not None and double_bottom.status == "neckline_broken" and any(
        f.type == "bearish_fvg" and f.status in ("open", "partial") for f in fvgs or []
    ):
        sell_score = max(0.0, sell_score - 0.08)
        warnings.append("CONFLICT_BEARISH_FVG_VS_DOUBLE_BOTTOM")
        conflict_flags.append("BEARISH_FVG_VS_DOUBLE_BOTTOM")

    return clamp_score(buy_score), clamp_score(sell_score), warnings, conflict_flags
