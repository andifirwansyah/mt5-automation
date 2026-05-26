"""Service layer for OHLCV validation."""

from dataclasses import dataclass

import pandas as pd

from .contracts import OHLCVValidationRequest
from .errors import OHLCVValidationInputError
from .models import OHLCVValidationResult, ValidatedOHLCVFrame

_REQUIRED_COLUMNS: tuple[str, ...] = ("timestamp", "open", "high", "low", "close", "volume")
_NUMERIC_PRICE_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close")


@dataclass(slots=True)
class OHLCVValidationOutput:
    """Combined output to keep result report-friendly."""

    result: OHLCVValidationResult
    validated_frame: ValidatedOHLCVFrame | None


class OHLCVValidationService:
    """Validate OHLCV frame integrity before downstream usage."""

    def validate(self, request: OHLCVValidationRequest) -> OHLCVValidationOutput:
        """Run strict checks and return validation result with optional validated frame."""
        if request.raw_frame is None or request.raw_frame.frame is None:
            raise OHLCVValidationInputError("raw_frame and frame must be provided.")

        frame = request.raw_frame.frame.copy()
        errors: list[str] = []
        warnings: list[str] = []

        missing_columns = [column for column in _REQUIRED_COLUMNS if column not in frame.columns]
        if missing_columns:
            errors.append(f"Missing required columns: {missing_columns}")
            result = self._build_result(
                request=request,
                errors=errors,
                warnings=warnings,
                frame=frame,
            )
            return OHLCVValidationOutput(result=result, validated_frame=None)

        parsed_timestamps = pd.to_datetime(frame["timestamp"], errors="coerce", utc=False)
        if parsed_timestamps.isna().any():
            invalid_count = int(parsed_timestamps.isna().sum())
            errors.append(f"Invalid timestamp value count: {invalid_count}")
        else:
            duplicate_count = int(parsed_timestamps.duplicated().sum())
            if duplicate_count > 0:
                errors.append(f"Duplicate timestamp detected: {duplicate_count}")

            if not parsed_timestamps.is_monotonic_increasing:
                errors.append("Timestamp order is not ascending.")

        for column in _NUMERIC_PRICE_COLUMNS:
            numeric_values = pd.to_numeric(frame[column], errors="coerce")
            if numeric_values.isna().any():
                invalid_count = int(numeric_values.isna().sum())
                errors.append(f"Non-numeric value detected in '{column}': {invalid_count}")
            frame[column] = numeric_values

        numeric_volume = pd.to_numeric(frame["volume"], errors="coerce")
        if numeric_volume.isna().any():
            invalid_count = int(numeric_volume.isna().sum())
            errors.append(f"Non-numeric value detected in 'volume': {invalid_count}")
        frame["volume"] = numeric_volume

        missing_value_count = int(frame[list(_REQUIRED_COLUMNS)].isna().sum().sum())
        if missing_value_count > 0:
            errors.append(f"Missing value detected in OHLCV fields: {missing_value_count}")

        invalid_high_low = int((frame["high"] < frame["low"]).sum())
        if invalid_high_low > 0:
            errors.append(f"Invalid candle high < low count: {invalid_high_low}")

        invalid_open_range = int(((frame["open"] < frame["low"]) | (frame["open"] > frame["high"])).sum())
        if invalid_open_range > 0:
            errors.append(f"Invalid candle open outside low-high range count: {invalid_open_range}")

        invalid_close_range = int(
            ((frame["close"] < frame["low"]) | (frame["close"] > frame["high"])).sum()
        )
        if invalid_close_range > 0:
            errors.append(f"Invalid candle close outside low-high range count: {invalid_close_range}")

        non_positive_volume = int((frame["volume"] < 0).sum())
        if non_positive_volume > 0:
            warnings.append(f"Negative volume detected count: {non_positive_volume}")

        if frame.empty:
            warnings.append("Frame is empty.")

        result = self._build_result(
            request=request,
            errors=errors,
            warnings=warnings,
            frame=frame,
        )

        validated: ValidatedOHLCVFrame | None = None
        if result.is_valid:
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=False)
            validated = ValidatedOHLCVFrame(
                symbol=request.raw_frame.symbol,
                timeframe=request.raw_frame.timeframe,
                frame=frame,
            )

        return OHLCVValidationOutput(result=result, validated_frame=validated)

    def _build_result(
        self,
        request: OHLCVValidationRequest,
        errors: list[str],
        warnings: list[str],
        frame: pd.DataFrame,
    ) -> OHLCVValidationResult:
        start_time = None
        end_time = None
        if "timestamp" in frame.columns:
            parsed_timestamps = pd.to_datetime(frame["timestamp"], errors="coerce", utc=False)
            valid_timestamps = parsed_timestamps.dropna()
            start_time = valid_timestamps.min().to_pydatetime() if not valid_timestamps.empty else None
            end_time = valid_timestamps.max().to_pydatetime() if not valid_timestamps.empty else None

        return OHLCVValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            row_count=int(len(frame.index)),
            start_time=start_time,
            end_time=end_time,
            timeframe=request.raw_frame.timeframe,
            symbol=request.raw_frame.symbol,
        )
