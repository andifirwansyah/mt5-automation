"""Service layer for rule-based market regime detection."""

from dataclasses import dataclass

import pandas as pd

from .contracts import MarketRegimeRequest, MarketRegimeThresholds
from .errors import MarketRegimeInputError
from .models import MarketRegimeResult


@dataclass(slots=True)
class _RegimeMetrics:
    trend_strength: float
    net_return: float
    avg_true_range_ratio: float
    range_width_ratio: float
    direction_consistency: float
    choppy_change_ratio: float


class MarketRegimeService:
    """Detect market regime from validated OHLCV frame."""

    def detect(self, request: MarketRegimeRequest) -> MarketRegimeResult:
        """Detect regime using strict rule-based metrics and configurable thresholds."""
        if request.primary_frame is None or request.primary_frame.frame is None:
            raise MarketRegimeInputError("primary_frame and frame must be provided.")

        frame = request.primary_frame.frame.copy()
        thresholds = request.thresholds
        notes: list[str] = []

        if len(frame.index) < thresholds.min_rows:
            notes.append(
                f"Insufficient data rows ({len(frame.index)}), minimum required {thresholds.min_rows}."
            )
            return MarketRegimeResult(
                symbol=request.primary_frame.symbol,
                timeframe=request.primary_frame.timeframe,
                regime="UNKNOWN",
                confidence=0.0,
                volatility_state="UNKNOWN",
                trend_strength=0.0,
                range_state="UNKNOWN",
                notes=notes,
            )

        metrics = self._calculate_metrics(frame)
        volatility_state = self._resolve_volatility_state(metrics.avg_true_range_ratio, thresholds)
        range_state = self._resolve_range_state(metrics.range_width_ratio, thresholds)

        regime = "UNKNOWN"
        confidence = 0.20

        is_trending = (
            metrics.trend_strength >= thresholds.trend_strength_min
            and metrics.direction_consistency >= thresholds.trend_direction_consistency_min
        )
        if is_trending:
            regime = "TREND_UP" if metrics.net_return >= 0 else "TREND_DOWN"
            confidence = self._trend_confidence(metrics, thresholds)
            notes.append(
                "Trend detected by trend strength and directional consistency thresholds."
            )
        else:
            is_range = (
                metrics.range_width_ratio <= thresholds.range_width_max
                and metrics.trend_strength < thresholds.trend_strength_min
            )
            if is_range:
                regime = "RANGE"
                confidence = self._range_confidence(metrics, thresholds)
                notes.append("Range detected by narrow width and low trend strength.")
            elif metrics.choppy_change_ratio >= thresholds.choppy_change_ratio_min:
                regime = "CHOPPY"
                confidence = min(1.0, 0.45 + (metrics.choppy_change_ratio - 0.5))
                notes.append("Choppy regime detected by alternating close changes.")
            elif volatility_state == "HIGH_VOLATILITY":
                regime = "HIGH_VOLATILITY"
                confidence = min(1.0, 0.55 + (metrics.avg_true_range_ratio * 5.0))
                notes.append("High volatility detected without strong directional trend.")
            elif volatility_state == "LOW_VOLATILITY":
                regime = "LOW_VOLATILITY"
                confidence = 0.55
                notes.append("Low volatility detected with muted candle movement.")

        context_bonus, context_note = self._context_alignment_bonus(
            primary_net_return=metrics.net_return,
            context_frames=request.context_frames,
            thresholds=thresholds,
        )
        if context_note is not None:
            notes.append(context_note)
        confidence = min(1.0, max(0.0, confidence + context_bonus))

        return MarketRegimeResult(
            symbol=request.primary_frame.symbol,
            timeframe=request.primary_frame.timeframe,
            regime=regime,
            confidence=round(confidence, 4),
            volatility_state=volatility_state,
            trend_strength=round(metrics.trend_strength, 6),
            range_state=range_state,
            notes=notes,
        )

    def _calculate_metrics(self, frame: pd.DataFrame) -> _RegimeMetrics:
        required_columns = {"open", "high", "low", "close"}
        if not required_columns.issubset(frame.columns):
            missing_columns = sorted(required_columns.difference(frame.columns))
            raise MarketRegimeInputError(f"Missing required frame columns: {missing_columns}")

        close_prices = pd.to_numeric(frame["close"], errors="coerce")
        open_prices = pd.to_numeric(frame["open"], errors="coerce")
        high_prices = pd.to_numeric(frame["high"], errors="coerce")
        low_prices = pd.to_numeric(frame["low"], errors="coerce")

        if close_prices.isna().any() or open_prices.isna().any() or high_prices.isna().any() or low_prices.isna().any():
            raise MarketRegimeInputError("Non-numeric OHLC values found in validated frame.")

        baseline_price = float(close_prices.iloc[0])
        if baseline_price <= 0:
            raise MarketRegimeInputError("Baseline close price must be positive.")

        net_return = float((close_prices.iloc[-1] - close_prices.iloc[0]) / close_prices.iloc[0])
        trend_strength = abs(net_return)

        intrabar_true_range = (high_prices - low_prices).abs()
        avg_true_range_ratio = float((intrabar_true_range / close_prices).mean())

        width_high = float(high_prices.max())
        width_low = float(low_prices.min())
        range_width_ratio = float((width_high - width_low) / baseline_price)

        close_delta = close_prices.diff().dropna()
        positive_moves = int((close_delta > 0).sum())
        negative_moves = int((close_delta < 0).sum())
        total_moves = max(1, positive_moves + negative_moves)
        dominant_moves = max(positive_moves, negative_moves)
        direction_consistency = dominant_moves / total_moves

        sign_changes = int((close_delta.shift(1) * close_delta < 0).sum())
        choppy_change_ratio = sign_changes / max(1, len(close_delta) - 1)

        return _RegimeMetrics(
            trend_strength=trend_strength,
            net_return=net_return,
            avg_true_range_ratio=avg_true_range_ratio,
            range_width_ratio=range_width_ratio,
            direction_consistency=direction_consistency,
            choppy_change_ratio=choppy_change_ratio,
        )

    def _resolve_volatility_state(
        self,
        avg_true_range_ratio: float,
        thresholds: MarketRegimeThresholds,
    ) -> str:
        if avg_true_range_ratio >= thresholds.high_volatility_min:
            return "HIGH_VOLATILITY"
        if avg_true_range_ratio <= thresholds.low_volatility_max:
            return "LOW_VOLATILITY"
        return "NORMAL_VOLATILITY"

    def _resolve_range_state(self, range_width_ratio: float, thresholds: MarketRegimeThresholds) -> str:
        return "TIGHT_RANGE" if range_width_ratio <= thresholds.range_width_max else "WIDE_RANGE"

    def _trend_confidence(self, metrics: _RegimeMetrics, thresholds: MarketRegimeThresholds) -> float:
        strength_ratio = metrics.trend_strength / max(thresholds.trend_strength_min, 1e-6)
        consistency_ratio = metrics.direction_consistency / max(
            thresholds.trend_direction_consistency_min,
            1e-6,
        )
        strength_score = min(1.0, strength_ratio / 2.0)
        consistency_score = min(1.0, consistency_ratio / 1.5)
        return min(1.0, 0.45 + (strength_score * 0.30) + (consistency_score * 0.25))

    def _range_confidence(self, metrics: _RegimeMetrics, thresholds: MarketRegimeThresholds) -> float:
        width_score = 1.0 - min(1.0, metrics.range_width_ratio / max(thresholds.range_width_max, 1e-6))
        trend_score = 1.0 - min(1.0, metrics.trend_strength / max(thresholds.trend_strength_min, 1e-6))
        return min(1.0, 0.40 + (width_score * 0.35) + (trend_score * 0.25))

    def _context_alignment_bonus(
        self,
        primary_net_return: float,
        context_frames: dict[str, object],
        thresholds: MarketRegimeThresholds,
    ) -> tuple[float, str | None]:
        if not context_frames:
            return 0.0, None

        primary_direction = 1 if primary_net_return >= 0 else -1
        aligned = 0
        checked = 0

        for timeframe, context_frame in context_frames.items():
            if context_frame is None or getattr(context_frame, "frame", None) is None:
                continue

            frame = context_frame.frame
            if len(frame.index) < thresholds.min_rows or "close" not in frame.columns:
                continue

            close_prices = pd.to_numeric(frame["close"], errors="coerce")
            if close_prices.isna().any() or close_prices.iloc[0] == 0:
                continue

            checked += 1
            context_return = float((close_prices.iloc[-1] - close_prices.iloc[0]) / close_prices.iloc[0])
            context_direction = 1 if context_return >= 0 else -1
            if context_direction == primary_direction:
                aligned += 1

        if checked == 0:
            return 0.0, "Context frames provided but none qualified for alignment check."

        alignment_ratio = aligned / checked
        bonus = (alignment_ratio - 0.5) * 0.2
        note = f"Context alignment ratio: {aligned}/{checked} ({alignment_ratio:.2f})."
        return bonus, note
