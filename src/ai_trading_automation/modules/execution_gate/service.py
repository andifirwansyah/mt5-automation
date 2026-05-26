"""Service layer for conservative execution gate decisions."""

from datetime import UTC, datetime

from .contracts import ExecutionGateRequest
from .errors import ExecutionGateInputError
from .models import ExecutionDecision


class ExecutionGateService:
    """Decide APPROVE/REDUCE_RISK/WAIT/REJECT before execution stage."""

    def decide(self, request: ExecutionGateRequest) -> ExecutionDecision:
        """Apply conservative gate policy from validation, risk, and simulation."""
        self._validate_request(request)

        signal_validation = request.signal_validation
        risk_plan = request.risk_plan
        simulation = request.simulation_result
        thresholds = request.thresholds
        signal = signal_validation.validated_signal

        if not signal_validation.is_valid or signal is None:
            reason = signal_validation.rejection_reason or "Signal validation failed."
            return self._build_decision(
                decision="REJECT",
                reason=f"Reject: invalid signal. {reason}",
                risk_plan=risk_plan,
                signal=signal,
            )

        if signal_validation.score < thresholds.min_signal_score:
            return self._build_decision(
                decision="WAIT",
                reason=(
                    "Wait: signal score below minimum threshold "
                    f"({signal_validation.score:.2f} < {thresholds.min_signal_score:.2f})."
                ),
                risk_plan=risk_plan,
                signal=signal,
            )

        if not simulation.passed:
            return self._build_decision(
                decision="WAIT",
                reason="Wait: pre-trade simulation failed under current assumptions.",
                risk_plan=risk_plan,
                signal=signal,
            )

        if risk_plan.risk_reward_ratio < thresholds.min_risk_reward_ratio:
            return self._build_decision(
                decision="REJECT",
                reason=(
                    "Reject: risk-reward ratio below acceptable minimum "
                    f"({risk_plan.risk_reward_ratio:.2f} < {thresholds.min_risk_reward_ratio:.2f})."
                ),
                risk_plan=risk_plan,
                signal=signal,
            )

        if risk_plan.risk_percent >= thresholds.reduce_risk_percent_threshold:
            return self._build_decision(
                decision="REDUCE_RISK",
                reason=(
                    "Reduce risk: requested risk percent is near max threshold "
                    f"({risk_plan.risk_percent:.2f}% >= {thresholds.reduce_risk_percent_threshold:.2f}%)."
                ),
                risk_plan=risk_plan,
                signal=signal,
            )

        return self._build_decision(
            decision="APPROVE",
            reason="Approve: signal valid, risk acceptable, and simulation passed.",
            risk_plan=risk_plan,
            signal=signal,
        )

    def _build_decision(
        self,
        decision: str,
        reason: str,
        risk_plan,
        signal,
    ) -> ExecutionDecision:
        return ExecutionDecision(
            decision=decision,
            reason=reason,
            risk_plan=risk_plan,
            signal=signal,
            created_at=datetime.now(tz=UTC),
        )

    def _validate_request(self, request: ExecutionGateRequest) -> None:
        if request.signal_validation is None:
            raise ExecutionGateInputError("signal_validation must be provided.")
        if request.risk_plan is None:
            raise ExecutionGateInputError("risk_plan must be provided.")
        if request.simulation_result is None:
            raise ExecutionGateInputError("simulation_result must be provided.")
