"""Models for pre-trade simulation results."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class SimulationResult:
    """Result for deterministic pre-trade simulation stage."""

    passed: bool
    scenario_results: dict[str, float | bool | str]
    estimated_slippage: float
    spread_risk: float
    worst_case_loss: float
    notes: list[str] = field(default_factory=list)
