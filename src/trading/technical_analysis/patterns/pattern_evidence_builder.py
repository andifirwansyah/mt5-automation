"""Build technical analysis evidence output from detected patterns."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.trading.technical_analysis.models import DoubleBottomPattern, DoubleTopPattern, FVG, PatternEvidence, TechnicalAnalysisResult
from src.trading.technical_analysis.scoring import clamp_score, compute_side_scores


def build_pattern_evidence(
    double_top: DoubleTopPattern | None,
    double_bottom: DoubleBottomPattern | None,
    fvgs: list[FVG] | None = None,
) -> list[PatternEvidence]:
    evidence: list[PatternEvidence] = []

    if double_top is not None:
        signal = "sell" if double_top.status in ("neckline_broken", "weak_neckline_break", "waiting_neckline_break") else "neutral"
        evidence.append(
            PatternEvidence(
                pattern_type="DOUBLE_TOP",
                signal=signal,
                confidence=double_top.confidence,
                details={
                    "status": double_top.status,
                    "neckline": double_top.neckline,
                    "left_peak": double_top.left_peak.price,
                    "right_peak": double_top.right_peak.price,
                    "warnings": list(double_top.warnings),
                    "rejection_reason": double_top.rejection_reason,
                    **double_top.details,
                },
            )
        )

    if double_bottom is not None:
        signal = "buy" if double_bottom.status in ("neckline_broken", "weak_neckline_break", "waiting_neckline_break") else "neutral"
        evidence.append(
            PatternEvidence(
                pattern_type="DOUBLE_BOTTOM",
                signal=signal,
                confidence=double_bottom.confidence,
                details={
                    "status": double_bottom.status,
                    "neckline": double_bottom.neckline,
                    "left_bottom": double_bottom.left_bottom.price,
                    "right_bottom": double_bottom.right_bottom.price,
                    "warnings": list(double_bottom.warnings),
                    "rejection_reason": double_bottom.rejection_reason,
                    **double_bottom.details,
                },
            )
        )

    for fvg in fvgs or []:
        evidence.append(
            PatternEvidence(
                pattern_type="FVG",
                signal="buy" if fvg.type == "bullish_fvg" else "sell",
                confidence=fvg.confidence,
                fvgs=[fvg],
                details={
                    "type": fvg.type,
                    "low": fvg.low,
                    "high": fvg.high,
                    "midpoint": fvg.midpoint,
                    "status": fvg.status,
                    "age_bars": fvg.age_bars,
                    "filled_percent": fvg.filled_percent,
                },
            )
        )

    return evidence


def build_technical_analysis_result(
    symbol: str,
    timeframe: str,
    trace_id: str,
    double_top: DoubleTopPattern | None,
    double_bottom: DoubleBottomPattern | None,
    fvgs: list[FVG] | None = None,
    regime: str | None = None,
    sweep_detected: bool = False,
    warnings: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> TechnicalAnalysisResult:
    """Compose final TechnicalAnalysisResult from pattern detectors."""

    warning_list = list(warnings or [])
    evidence = build_pattern_evidence(double_top=double_top, double_bottom=double_bottom, fvgs=fvgs)
    buy_score, sell_score, conflict_warnings, conflict_flags = compute_side_scores(
        double_top=double_top,
        double_bottom=double_bottom,
        fvgs=fvgs,
    )
    warning_list.extend(conflict_warnings)

    bias = "neutral"
    if (buy_score - sell_score) >= 0.12:
        bias = "buy"
    elif (sell_score - buy_score) >= 0.12:
        bias = "sell"

    strategy_hints: list[str] = []
    if double_top is not None and double_top.status == "neckline_broken":
        strategy_hints.extend(["RANGE_REVERSION", "VOLATILITY_BREAKOUT"])
    if double_bottom is not None and double_bottom.status == "neckline_broken":
        strategy_hints.extend(["RANGE_REVERSION", "VOLATILITY_BREAKOUT"])

    regime_value = (regime or "").upper()
    if "TRENDING" in regime_value:
        if any(f.type == "bullish_fvg" and f.status in ("open", "partial") for f in fvgs or []):
            strategy_hints.append("EMA_ATR_TREND")
        if any(f.type == "bearish_fvg" and f.status in ("open", "partial") for f in fvgs or []):
            strategy_hints.append("EMA_ATR_TREND")

    if sweep_detected and (
        (fvgs and len(fvgs) > 0)
        or (double_top is not None)
        or (double_bottom is not None)
    ):
        strategy_hints.append("LIQUIDITY_SWEEP_REVERSAL")

    # keep unique order
    seen: set[str] = set()
    strategy_hints = [h for h in strategy_hints if not (h in seen or seen.add(h))]

    technical_score = clamp_score(max(buy_score, sell_score) - (0.01 * len(warning_list)))

    meta = dict(metadata or {})
    meta["trace_id"] = trace_id

    return TechnicalAnalysisResult(
        symbol=symbol,
        timeframe=timeframe,
        bias=bias,
        technical_score=technical_score,
        buy_score=buy_score,
        sell_score=sell_score,
        pattern_evidence=evidence,
        warnings=warning_list,
        strategy_hints=strategy_hints,
        conflict_flags=conflict_flags,
        metadata=meta,
        analyzed_at=datetime.now(timezone.utc),
    )
