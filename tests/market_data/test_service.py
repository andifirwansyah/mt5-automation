from pathlib import Path

import pandas as pd
import pytest

from ai_trading_automation.modules.market_data import (
    DatasetFileNotFoundError,
    DatasetLoadRequest,
    MarketDataLoaderService,
)


def _write_csv(file_path: Path) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2026-01-01 00:00:00,100,110,90,105,10\n",
        encoding="utf-8",
    )


def _write_semicolon_csv(file_path: Path) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        "Date;Open;High;Low;Close;Volume\n"
        "2026-01-01 00:00:00;100;110;90;105;10\n",
        encoding="utf-8",
    )


def test_load_valid_file_normalize_columns(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    csv_path = dataset_root / "H1" / "xauusd_h1.csv"
    _write_csv(csv_path)

    service = MarketDataLoaderService()
    request = DatasetLoadRequest(dataset_path=dataset_root, symbol="xauusd", timeframe="H1")

    result = service.load_timeframe(request)

    assert result.symbol == "XAUUSD"
    assert result.timeframe == "H1"
    assert list(result.frame.columns[:6]) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert result.frame.loc[0, "timestamp"] == "2026-01-01 00:00:00"
    assert result.frame.loc[0, "symbol"] == "XAUUSD"
    assert result.frame.loc[0, "timeframe"] == "H1"


def test_load_timeframe_missing_file_raises_error(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    (dataset_root / "M15").mkdir(parents=True, exist_ok=True)

    service = MarketDataLoaderService()
    request = DatasetLoadRequest(dataset_path=dataset_root, symbol="XAUUSD", timeframe="M15")

    with pytest.raises(DatasetFileNotFoundError):
        service.load_timeframe(request)


def test_load_semicolon_delimited_csv(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    csv_path = dataset_root / "H1" / "xauusd_h1_semicolon.csv"
    _write_semicolon_csv(csv_path)

    service = MarketDataLoaderService()
    request = DatasetLoadRequest(dataset_path=dataset_root, symbol="xauusd", timeframe="H1")

    result = service.load_timeframe(request)

    assert list(result.frame.columns[:6]) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert result.frame.loc[0, "open"] == 100


def test_unsupported_timeframe_raises_validation_error(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"

    with pytest.raises(ValueError, match="Unsupported timeframe"):
        DatasetLoadRequest(dataset_path=dataset_root, symbol="XAUUSD", timeframe="M1")


def test_load_all_supported_timeframes(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    for timeframe in ("D1", "H4", "H1", "M30", "M15", "M5"):
        _write_csv(dataset_root / timeframe / f"xauusd_{timeframe.lower()}.csv")

    service = MarketDataLoaderService()
    result = service.load_all_timeframes(dataset_path=dataset_root, symbol="XAUUSD")

    assert set(result.keys()) == {"D1", "H4", "H1", "M30", "M15", "M5"}
    assert all(isinstance(item.frame, pd.DataFrame) for item in result.values())
