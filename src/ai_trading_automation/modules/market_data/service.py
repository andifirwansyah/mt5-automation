"""Service layer for loading OHLCV dataset files per timeframe."""

from pathlib import Path

import pandas as pd

from .contracts import DatasetLoadRequest, SUPPORTED_TIMEFRAMES
from .errors import DatasetFileNotFoundError, DatasetFormatError, UnsupportedTimeframeError
from .models import OHLCVFrame

_REQUIRED_COLUMNS: tuple[str, ...] = ("timestamp", "open", "high", "low", "close", "volume")
_COLUMN_ALIASES: dict[str, str] = {
    "timestamp": "timestamp",
    "time": "timestamp",
    "datetime": "timestamp",
    "date": "timestamp",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
    "vol": "volume",
    "tick_volume": "volume",
}
_SUPPORTED_FILE_EXTENSIONS: tuple[str, ...] = (".csv", ".parquet")


class MarketDataLoaderService:
    """Load OHLCV dataset from local timeframe folders."""

    def load_timeframe(self, request: DatasetLoadRequest) -> OHLCVFrame:
        """Load one timeframe file and return normalized raw OHLCV frame."""
        if request.timeframe not in SUPPORTED_TIMEFRAMES:
            raise UnsupportedTimeframeError(
                f"Unsupported timeframe '{request.timeframe}'. "
                f"Supported: {', '.join(SUPPORTED_TIMEFRAMES)}"
            )

        timeframe_dir = request.dataset_path / request.timeframe
        if not timeframe_dir.exists() or not timeframe_dir.is_dir():
            raise DatasetFileNotFoundError(
                f"Timeframe directory not found for '{request.timeframe}': {timeframe_dir}"
            )

        dataset_file = self._resolve_dataset_file(timeframe_dir)
        frame = self._read_file(dataset_file)
        normalized = self._normalize_columns(frame)
        normalized["symbol"] = request.symbol
        normalized["timeframe"] = request.timeframe

        return OHLCVFrame(
            symbol=request.symbol,
            timeframe=request.timeframe,
            frame=normalized,
        )

    def load_all_timeframes(self, dataset_path: Path, symbol: str) -> dict[str, OHLCVFrame]:
        """Load all supported timeframes and return mapped OHLCV frames."""
        result: dict[str, OHLCVFrame] = {}
        for timeframe in SUPPORTED_TIMEFRAMES:
            request = DatasetLoadRequest(dataset_path=dataset_path, symbol=symbol, timeframe=timeframe)
            result[timeframe] = self.load_timeframe(request)
        return result

    def _resolve_dataset_file(self, timeframe_dir: Path) -> Path:
        files = sorted(
            file_path
            for file_path in timeframe_dir.iterdir()
            if file_path.is_file() and file_path.suffix.lower() in _SUPPORTED_FILE_EXTENSIONS
        )
        if not files:
            supported = ", ".join(_SUPPORTED_FILE_EXTENSIONS)
            raise DatasetFileNotFoundError(
                f"No dataset file found in {timeframe_dir}. Supported extensions: {supported}"
            )
        return files[0]

    def _read_file(self, file_path: Path) -> pd.DataFrame:
        suffix = file_path.suffix.lower()
        try:
            if suffix == ".csv":
                # Use delimiter auto-detection so MT5 exports like
                # "Date;Open;High;Low;Close;Volume" are supported.
                return pd.read_csv(file_path, sep=None, engine="python")
            if suffix == ".parquet":
                return pd.read_parquet(file_path)
        except Exception as error:  # pragma: no cover - pandas errors differ by parser/backend
            raise DatasetFormatError(f"Failed to parse dataset file {file_path}: {error}") from error

        raise DatasetFormatError(
            f"Unsupported dataset file extension '{suffix}' for {file_path}."
        )

    def _normalize_columns(self, frame: pd.DataFrame) -> pd.DataFrame:
        renamed = frame.rename(columns=self._build_rename_map(frame.columns))
        normalized_columns = set(renamed.columns)
        missing_columns = [column for column in _REQUIRED_COLUMNS if column not in normalized_columns]
        if missing_columns:
            raise DatasetFormatError(
                f"Missing required OHLCV columns after normalization: {missing_columns}"
            )

        ordered_columns = [* _REQUIRED_COLUMNS]
        extra_columns = [column for column in renamed.columns if column not in ordered_columns]
        return renamed[[*ordered_columns, *extra_columns]].copy()

    def _build_rename_map(self, columns: pd.Index) -> dict[str, str]:
        rename_map: dict[str, str] = {}
        for original in columns:
            normalized = str(original).strip().lower().replace(" ", "_")
            mapped = _COLUMN_ALIASES.get(normalized, normalized)
            rename_map[str(original)] = mapped
        return rename_map
