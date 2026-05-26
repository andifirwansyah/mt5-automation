import pandas as pd

from ai_trading_automation.modules.market_data.models import OHLCVFrame
from ai_trading_automation.modules.ohlcv_validation import (
    OHLCVValidationRequest,
    OHLCVValidationService,
)


def _build_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [
                "2026-01-01 00:00:00",
                "2026-01-01 01:00:00",
                "2026-01-01 02:00:00",
            ],
            "open": [100.0, 101.0, 102.0],
            "high": [105.0, 106.0, 107.0],
            "low": [99.0, 100.0, 101.0],
            "close": [104.0, 102.0, 103.0],
            "volume": [10.0, 11.0, 12.0],
        }
    )


def _build_request(frame: pd.DataFrame) -> OHLCVValidationRequest:
    return OHLCVValidationRequest(
        raw_frame=OHLCVFrame(
            symbol="XAUUSD",
            timeframe="H1",
            frame=frame,
        )
    )


def test_validate_valid_ohlcv_frame() -> None:
    service = OHLCVValidationService()
    output = service.validate(_build_request(_build_frame()))

    assert output.result.is_valid is True
    assert output.result.errors == []
    assert output.validated_frame is not None


def test_validate_high_less_than_low_detected() -> None:
    frame = _build_frame()
    frame.loc[1, "high"] = 90.0

    service = OHLCVValidationService()
    output = service.validate(_build_request(frame))

    assert output.result.is_valid is False
    assert any("high < low" in message for message in output.result.errors)
    assert output.validated_frame is None


def test_validate_duplicate_timestamp_detected() -> None:
    frame = _build_frame()
    frame.loc[1, "timestamp"] = frame.loc[0, "timestamp"]

    service = OHLCVValidationService()
    output = service.validate(_build_request(frame))

    assert output.result.is_valid is False
    assert any("Duplicate timestamp" in message for message in output.result.errors)


def test_validate_missing_close_column_detected() -> None:
    frame = _build_frame().drop(columns=["close"])

    service = OHLCVValidationService()
    output = service.validate(_build_request(frame))

    assert output.result.is_valid is False
    assert any("Missing required columns" in message for message in output.result.errors)
