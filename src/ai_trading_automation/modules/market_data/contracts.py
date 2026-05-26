"""Contracts for market data dataset loading."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator

SUPPORTED_TIMEFRAMES: tuple[str, ...] = ("D1", "H4", "H1", "M30", "M15", "M5")


class DatasetLoadRequest(BaseModel):
    """Input contract to load one OHLCV timeframe file."""

    model_config = ConfigDict(str_strip_whitespace=True)

    dataset_path: Path
    symbol: str
    timeframe: str

    @field_validator("timeframe", mode="before")
    @classmethod
    def validate_timeframe(cls, value: str) -> str:
        normalized = str(value).upper()
        if normalized not in SUPPORTED_TIMEFRAMES:
            supported = ", ".join(SUPPORTED_TIMEFRAMES)
            raise ValueError(f"Unsupported timeframe '{value}'. Supported: {supported}")
        return normalized

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return str(value).upper()

    @field_validator("dataset_path", mode="before")
    @classmethod
    def normalize_dataset_path(cls, value: str | Path) -> Path:
        return Path(value)
