"""Contracts for signal normalization module."""

from dataclasses import dataclass

from ai_trading_automation.modules.strategy_engine.models import RawSignalCandidate


@dataclass(slots=True)
class SignalContractBuildRequest:
    """Input contract to build standardized signal contract."""

    raw_candidate: RawSignalCandidate
