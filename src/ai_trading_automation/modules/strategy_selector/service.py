"""Service layer for mapping market regime into strategy selection."""

from dataclasses import dataclass

from .contracts import StrategySelectorRequest
from .errors import StrategySelectorInputError
from .models import SelectedStrategy


@dataclass(frozen=True, slots=True)
class _StrategyRule:
    strategy_key: str
    decision: str
    reason: str
    confidence_modifier: float
    candidates: list[str]


class StrategySelectorService:
    """Select trading strategy from market regime using explicit rule mapping."""

    _REGIME_RULES: dict[str, _StrategyRule] = {
        "TREND_UP": _StrategyRule(
            strategy_key="trend_follow_pullback",
            decision="SELECT",
            reason="Regime trend up cocok untuk trend-follow pullback strategy.",
            confidence_modifier=0.08,
            candidates=["trend_follow_pullback", "breakout_continuation"],
        ),
        "TREND_DOWN": _StrategyRule(
            strategy_key="trend_follow_pullback",
            decision="SELECT",
            reason="Regime trend down cocok untuk trend-follow pullback strategy.",
            confidence_modifier=0.08,
            candidates=["trend_follow_pullback", "breakout_continuation"],
        ),
        "RANGE": _StrategyRule(
            strategy_key="range_mean_reversion",
            decision="SELECT",
            reason="Regime range cocok untuk mean reversion strategy.",
            confidence_modifier=0.05,
            candidates=["range_mean_reversion", "support_resistance_retest"],
        ),
        "HIGH_VOLATILITY": _StrategyRule(
            strategy_key="volatility_breakout",
            decision="SELECT",
            reason="High volatility diarahkan ke breakout strategy dengan risk ketat.",
            confidence_modifier=0.03,
            candidates=["volatility_breakout", "momentum_scalp"],
        ),
        "LOW_VOLATILITY": _StrategyRule(
            strategy_key="WAIT",
            decision="WAIT",
            reason="Low volatility: setup belum cukup menarik, tunggu kondisi lebih jelas.",
            confidence_modifier=-0.05,
            candidates=["range_mean_reversion"],
        ),
        "CHOPPY": _StrategyRule(
            strategy_key="WAIT",
            decision="WAIT",
            reason="Choppy market: hindari noise dan tunggu struktur lebih bersih.",
            confidence_modifier=-0.08,
            candidates=["range_mean_reversion", "trend_follow_pullback"],
        ),
        "BREAKOUT_RISK": _StrategyRule(
            strategy_key="WAIT",
            decision="WAIT",
            reason="Breakout risk tinggi: tunggu konfirmasi sebelum memilih strategy aktif.",
            confidence_modifier=-0.07,
            candidates=["volatility_breakout"],
        ),
        "UNKNOWN": _StrategyRule(
            strategy_key="WAIT",
            decision="WAIT",
            reason="Regime unknown: data/kondisi belum cukup untuk pemilihan strategy.",
            confidence_modifier=-0.10,
            candidates=[],
        ),
    }

    def select(self, request: StrategySelectorRequest) -> SelectedStrategy:
        """Return selected strategy or WAIT based on regime mapping rules."""
        regime_result = request.market_regime
        if regime_result is None:
            raise StrategySelectorInputError("market_regime must be provided.")

        if not 0.0 <= request.min_regime_confidence <= 1.0:
            raise StrategySelectorInputError("min_regime_confidence must be between 0 and 1.")

        base_rule = self._REGIME_RULES.get(regime_result.regime, self._REGIME_RULES["UNKNOWN"])

        reason_suffix = ""
        if regime_result.confidence < request.min_regime_confidence:
            base_rule = _StrategyRule(
                strategy_key="WAIT",
                decision="WAIT",
                reason="Confidence regime di bawah threshold minimum, keputusan WAIT.",
                confidence_modifier=-0.05,
                candidates=base_rule.candidates,
            )
            reason_suffix = (
                f" (confidence={regime_result.confidence:.2f}, "
                f"min={request.min_regime_confidence:.2f})"
            )

        final_confidence = min(1.0, max(0.0, regime_result.confidence + base_rule.confidence_modifier))
        return SelectedStrategy(
            symbol=regime_result.symbol,
            timeframe=regime_result.timeframe,
            regime=regime_result.regime,
            strategy_key=base_rule.strategy_key,
            decision=base_rule.decision,
            confidence=round(final_confidence, 4),
            reason=f"{base_rule.reason}{reason_suffix}",
            candidate_strategies=base_rule.candidates,
        )
