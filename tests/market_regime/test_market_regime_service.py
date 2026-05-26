from datetime import datetime, timedelta

import pandas as pd

from ai_trading_automation.modules.market_regime import MarketRegimeRequest, MarketRegimeService
from ai_trading_automation.modules.ohlcv_validation.models import ValidatedOHLCVFrame


def _validated_frame_from_close(close_values: list[float]) -> ValidatedOHLCVFrame:
    start = datetime(2026, 1, 1, 0, 0, 0)
    rows: list[dict[str, float | datetime]] = []
    for index, close_price in enumerate(close_values):
        open_price = close_values[index - 1] if index > 0 else close_price
        high_price = max(open_price, close_price) + 0.2
        low_price = min(open_price, close_price) - 0.2
        rows.append(
            {
                "timestamp": start + timedelta(hours=index),
                "open": float(open_price),
                "high": float(high_price),
                "low": float(low_price),
                "close": float(close_price),
                "volume": 10.0 + index,
            }
        )

    return ValidatedOHLCVFrame(
        symbol="XAUUSD",
        timeframe="H1",
        frame=pd.DataFrame(rows),
    )


def test_detect_trend_up_regime() -> None:
    close_values = [100.0 + (index * 0.25) for index in range(60)]
    service = MarketRegimeService()
    request = MarketRegimeRequest(primary_frame=_validated_frame_from_close(close_values))

    result = service.detect(request)

    assert result.regime == "TREND_UP"
    assert 0.0 <= result.confidence <= 1.0
    assert result.trend_strength > 0


def test_detect_range_regime() -> None:
    base = [100.0, 100.2, 99.9, 100.1, 99.8, 100.0]
    close_values = [base[index % len(base)] for index in range(60)]
    service = MarketRegimeService()
    request = MarketRegimeRequest(primary_frame=_validated_frame_from_close(close_values))

    result = service.detect(request)

    assert result.regime == "RANGE"
    assert 0.0 <= result.confidence <= 1.0


def test_detect_unknown_when_insufficient_data() -> None:
    close_values = [100.0 + (index * 0.1) for index in range(10)]
    service = MarketRegimeService()
    request = MarketRegimeRequest(primary_frame=_validated_frame_from_close(close_values))

    result = service.detect(request)

    assert result.regime == "UNKNOWN"
    assert result.confidence == 0.0
    assert any("Insufficient data" in note for note in result.notes)
