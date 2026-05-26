from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ai_trading_automation.modules.signal_contract import (
    SignalContract,
    SignalContractBuildError,
    SignalContractBuildRequest,
    SignalContractService,
)
from ai_trading_automation.modules.strategy_engine.models import RawSignalCandidate


def _raw_candidate(
    direction: str,
    metadata: dict[str, str | float | int | bool],
) -> RawSignalCandidate:
    return RawSignalCandidate(
        symbol="XAUUSD",
        timeframe="H1",
        strategy_key="trend_follow_pullback",
        direction=direction,
        confidence=0.71,
        reason="test raw candidate",
        created_at=datetime.now(tz=UTC),
        metadata=metadata,
    )


def test_build_valid_signal_contract() -> None:
    service = SignalContractService()
    request = SignalContractBuildRequest(
        raw_candidate=_raw_candidate(
            direction="BUY",
            metadata={
                "entry_price": 2350.5,
                "stop_loss": 2346.5,
                "take_profit": 2358.0,
            },
        )
    )

    signal = service.build(request)

    assert signal.direction.value == "BUY"
    assert signal.entry_price == 2350.5
    assert signal.stop_loss == 2346.5
    assert signal.take_profit == 2358.0
    assert signal.signal_id


def test_invalid_direction_fails_validation() -> None:
    with pytest.raises(ValidationError):
        SignalContract.model_validate(
            {
                "signal_id": "s-1",
                "symbol": "XAUUSD",
                "timeframe": "H1",
                "direction": "LONG",
                "entry_price": 2350.5,
                "stop_loss": 2346.5,
                "take_profit": 2358.0,
                "strategy_key": "trend_follow_pullback",
                "confidence": 0.5,
                "reason": "invalid direction",
                "created_at": datetime.now(tz=UTC),
                "metadata": {},
            }
        )


def test_missing_stop_loss_fails_build() -> None:
    service = SignalContractService()
    request = SignalContractBuildRequest(
        raw_candidate=_raw_candidate(
            direction="BUY",
            metadata={
                "entry_price": 2350.5,
                "take_profit": 2358.0,
            },
        )
    )

    with pytest.raises(SignalContractBuildError, match="Missing required price fields"):
        service.build(request)
