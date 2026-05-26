"""Service layer for deterministic pre-trade simulation."""

from .contracts import PreTradeSimulationRequest
from .errors import PreTradeSimulationInputError
from .models import SimulationResult


class PreTradeSimulationService:
    """Simulate spread/slippage/adverse movement before execution gate."""

    def run(self, request: PreTradeSimulationRequest) -> SimulationResult:
        """Run deterministic simulation and return pass/fail with notes."""
        self._validate_request(request)

        signal_validation = request.signal_validation
        risk_plan = request.risk_plan
        assumptions = request.assumptions
        notes: list[str] = []

        if not signal_validation.is_valid or signal_validation.validated_signal is None:
            notes.append("Signal validation is not valid for simulation input.")
            return SimulationResult(
                passed=False,
                scenario_results={"signal_input_valid": False},
                estimated_slippage=0.0,
                spread_risk=0.0,
                worst_case_loss=float(risk_plan.max_loss),
                notes=notes,
            )

        spread_risk = risk_plan.max_loss * assumptions.spread_percent
        estimated_slippage = risk_plan.max_loss * assumptions.slippage_percent
        adverse_loss = risk_plan.max_loss * assumptions.adverse_move_factor
        worst_case_loss = risk_plan.max_loss + spread_risk + estimated_slippage + adverse_loss

        spread_extreme = assumptions.spread_percent >= assumptions.spread_extreme_threshold
        slippage_extreme = assumptions.slippage_percent >= assumptions.slippage_extreme_threshold
        worst_case_limit = risk_plan.max_loss * assumptions.max_worst_case_loss_factor
        worst_case_exceeded = worst_case_loss > worst_case_limit

        if spread_extreme:
            notes.append(
                "Simulation failed: spread assumption exceeds extreme threshold "
                f"({assumptions.spread_percent:.4f} >= {assumptions.spread_extreme_threshold:.4f})."
            )
        if slippage_extreme:
            notes.append(
                "Simulation failed: slippage assumption exceeds extreme threshold "
                f"({assumptions.slippage_percent:.4f} >= {assumptions.slippage_extreme_threshold:.4f})."
            )
        if worst_case_exceeded:
            notes.append(
                "Simulation failed: worst-case loss exceeds allowed factor "
                f"({worst_case_loss:.2f} > {worst_case_limit:.2f})."
            )

        passed = not (spread_extreme or slippage_extreme or worst_case_exceeded)
        if passed:
            notes.append("Simulation passed under configured deterministic assumptions.")

        return SimulationResult(
            passed=passed,
            scenario_results={
                "signal_input_valid": True,
                "spread_extreme": spread_extreme,
                "slippage_extreme": slippage_extreme,
                "worst_case_exceeded": worst_case_exceeded,
                "worst_case_limit": round(worst_case_limit, 6),
            },
            estimated_slippage=round(estimated_slippage, 6),
            spread_risk=round(spread_risk, 6),
            worst_case_loss=round(worst_case_loss, 6),
            notes=notes,
        )

    def _validate_request(self, request: PreTradeSimulationRequest) -> None:
        if request.signal_validation is None:
            raise PreTradeSimulationInputError("signal_validation must be provided.")
        if request.risk_plan is None:
            raise PreTradeSimulationInputError("risk_plan must be provided.")

        assumptions = request.assumptions
        numeric_fields = {
            "spread_percent": assumptions.spread_percent,
            "slippage_percent": assumptions.slippage_percent,
            "adverse_move_factor": assumptions.adverse_move_factor,
            "max_worst_case_loss_factor": assumptions.max_worst_case_loss_factor,
        }
        for field_name, value in numeric_fields.items():
            if value < 0:
                raise PreTradeSimulationInputError(f"{field_name} cannot be negative.")

        if assumptions.max_worst_case_loss_factor < 1.0:
            raise PreTradeSimulationInputError("max_worst_case_loss_factor must be >= 1.0.")
