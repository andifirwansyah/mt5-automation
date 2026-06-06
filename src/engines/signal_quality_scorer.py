"""Signal quality scorer engine."""

from __future__ import annotations

from typing import Any

from src.config.settings import AppSettings, get_settings
from src.domain.enums import SignalDirection
from src.domain.models.signal_quality import SignalQualityResult
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext


class SignalQualityScorer(PipelineStep):
    """Score signal quality from confidence, technical, structure, RR, and spread context."""

    @property
    def name(self) -> str:
        return "SignalQualityScorer"

    def __init__(self, settings: AppSettings | Any | None = None) -> None:
        self.settings = settings or get_settings()

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, value))

    @staticmethod
    def _grade(score: float) -> str:
        if score >= 0.80:
            return "A"
        if score >= 0.65:
            return "B"
        if score >= 0.50:
            return "C"
        return "D"

    def run(self, context: TradingContext) -> TradingContext:
        if context.signal_contract is None:
            context.reject("SIGNAL_QUALITY_FAILED", {"message": "signal_contract missing"})
            return context

        signal = context.signal_contract
        reasons: list[str] = []
        warnings: list[str] = []

        confidence_score = self._clamp(float(signal.confidence or 0.0))

        technical_score = 0.50
        if context.technical_analysis is not None:
            technical_score = self._clamp(float(context.technical_analysis.technical_score or 0.0))
            bias = context.technical_analysis.bias
            if signal.direction == SignalDirection.BUY and bias == "sell":
                warnings.append("TECHNICAL_BIAS_CONFLICT")
                technical_score *= 0.65
            if signal.direction == SignalDirection.SELL and bias == "buy":
                warnings.append("TECHNICAL_BIAS_CONFLICT")
                technical_score *= 0.65
        else:
            warnings.append("TECHNICAL_ANALYSIS_MISSING")

        structure_score = 0.50
        if context.market_structure is not None:
            structure = context.market_structure
            if signal.direction == SignalDirection.BUY:
                structure_score = 0.80 if structure.valid_buy_zone else 0.45
                if structure.is_near_resistance:
                    structure_score = 0.20
                    warnings.append("BUY_NEAR_RESISTANCE")
            elif signal.direction == SignalDirection.SELL:
                structure_score = 0.80 if structure.valid_sell_zone else 0.45
                if structure.is_near_support:
                    structure_score = 0.20
                    warnings.append("SELL_NEAR_SUPPORT")
        else:
            warnings.append("MARKET_STRUCTURE_MISSING")

        entry = float(signal.entry_price)
        risk = abs(entry - float(signal.stop_loss))
        reward = abs(float(signal.take_profit) - entry)
        rr_ratio = reward / risk if risk > 0 else 0.0
        min_rr = max(0.01, float(getattr(self.settings, "min_rr", 1.0)))
        rr_score = self._clamp(rr_ratio / max(min_rr * 1.5, min_rr))
        if rr_ratio < min_rr:
            warnings.append("RR_BELOW_MINIMUM")

        spread_score = 1.0
        spread = context.market_snapshot.spread if context.market_snapshot else None
        max_spread = float(getattr(self.settings, "max_spread", 50.0))
        if spread is not None and max_spread > 0:
            spread_score = self._clamp(1.0 - (float(spread) / max_spread))
            if float(spread) > max_spread * 0.80:
                warnings.append("SPREAD_NEAR_LIMIT")

        score = self._clamp(
            (confidence_score * 0.30)
            + (technical_score * 0.25)
            + (structure_score * 0.25)
            + (rr_score * 0.15)
            + (spread_score * 0.05)
        )
        min_score = float(getattr(self.settings, "signal_quality_min_score", 0.45))
        passed = score >= min_score
        if not passed:
            reasons.append("SIGNAL_QUALITY_BELOW_MINIMUM")

        context.signal_quality = SignalQualityResult(
            passed=passed,
            score=round(score, 6),
            grade=self._grade(score),
            reasons=reasons,
            warnings=warnings,
            details={
                "confidence_score": confidence_score,
                "technical_score": technical_score,
                "structure_score": structure_score,
                "rr_ratio": rr_ratio,
                "rr_score": rr_score,
                "spread_score": spread_score,
                "min_score": min_score,
            },
        )

        if not passed:
            context.reject("SIGNAL_QUALITY_FAILED", context.signal_quality.details | {"reasons": reasons, "warnings": warnings})
        return context
