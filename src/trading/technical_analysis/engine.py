"""Technical Analysis Engine for chart evidence extraction."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger

from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.trading.technical_analysis.config import TechnicalAnalysisConfig
from src.trading.technical_analysis.models import PatternEvidence, TechnicalAnalysisResult
from src.trading.technical_analysis.patterns import (
    build_technical_analysis_result,
    detect_double_bottom_pattern,
    detect_double_top_pattern,
    detect_fvgs,
    detect_swing_points,
)
from src.trading.technical_analysis.scoring import clamp_score, compute_technical_score


class TechnicalAnalysisEngine(PipelineStep):
    """Produce non-blocking technical evidence for downstream engines."""

    @property
    def name(self) -> str:
        return "TechnicalAnalysisEngine"

    def __init__(self, config: TechnicalAnalysisConfig | None = None) -> None:
        self.config = config or TechnicalAnalysisConfig()

    @staticmethod
    def _to_candle_rows(frame_like: Any) -> list[dict[str, Any]]:
        if frame_like is None:
            return []
        if hasattr(frame_like, "to_dict") and hasattr(frame_like, "columns"):
            try:
                return list(frame_like.to_dict(orient="records"))
            except TypeError:
                pass
        if isinstance(frame_like, list):
            rows: list[dict[str, Any]] = []
            for row in frame_like:
                if isinstance(row, dict):
                    rows.append(row)
                else:
                    rows.append(dict(row))
            return rows
        return []

    def _extract_candles(self, context: TradingContext, timeframe: str) -> list[dict[str, Any]]:
        ingestion = context.ingestion_result or {}
        rates_by_timeframe = ingestion.get("rates_by_timeframe") or {}
        raw = rates_by_timeframe.get(timeframe)
        rows = self._to_candle_rows(raw)
        if len(rows) > self.config.max_candles_lookback:
            return rows[-self.config.max_candles_lookback :]
        return rows

    def _analyze_timeframe(
        self,
        *,
        context: TradingContext,
        timeframe: str,
        candles: list[dict[str, Any]],
        atr: float,
        regime_value: str | None,
        sweep_detected: bool,
        log: Any,
    ) -> TechnicalAnalysisResult:
        warnings: list[str] = []
        invalid_ohlc = any(float(c.get("high", 0.0)) < float(c.get("low", 0.0)) for c in candles)
        if invalid_ohlc:
            warnings.append("TECHNICAL_INVALID_OHLC")

        swing_highs, swing_lows = detect_swing_points(
            candles=candles,
            left_bars=self.config.swing.left_bars,
            right_bars=self.config.swing.right_bars,
            atr=atr,
            min_distance_atr=self.config.swing.min_distance_atr,
        )
        log.info("SWING_POINTS_DETECTED timeframe={} highs={} lows={}", timeframe, len(swing_highs), len(swing_lows))

        double_top = detect_double_top_pattern(
            candles=candles,
            swing_highs=swing_highs,
            swing_lows=swing_lows,
            atr=atr,
            config=self.config.double_top,
            neckline_config=self.config.neckline_break,
        )
        if double_top is not None:
            log.info("PATTERN_DETECTED timeframe={} type=DOUBLE_TOP status={}", timeframe, double_top.status)
            if double_top.status == "neckline_broken":
                log.info("PATTERN_CONFIRMED timeframe={} type=DOUBLE_TOP", timeframe)
            if double_top.rejection_reason:
                log.warning("PATTERN_REJECTED timeframe={} type=DOUBLE_TOP reason={}", timeframe, double_top.rejection_reason)
            warnings.extend(double_top.warnings)
        else:
            log.warning("PATTERN_REJECTED timeframe={} type=DOUBLE_TOP reason=NO_VALID_PATTERN", timeframe)

        double_bottom = detect_double_bottom_pattern(
            candles=candles,
            swing_highs=swing_highs,
            swing_lows=swing_lows,
            atr=atr,
            config=self.config.double_bottom,
            neckline_config=self.config.neckline_break,
        )
        if double_bottom is not None:
            log.info("PATTERN_DETECTED timeframe={} type=DOUBLE_BOTTOM status={}", timeframe, double_bottom.status)
            if double_bottom.status == "neckline_broken":
                log.info("PATTERN_CONFIRMED timeframe={} type=DOUBLE_BOTTOM", timeframe)
            if double_bottom.rejection_reason:
                log.warning(
                    "PATTERN_REJECTED timeframe={} type=DOUBLE_BOTTOM reason={}",
                    timeframe,
                    double_bottom.rejection_reason,
                )
            warnings.extend(double_bottom.warnings)
        else:
            log.warning("PATTERN_REJECTED timeframe={} type=DOUBLE_BOTTOM reason=NO_VALID_PATTERN", timeframe)

        fvgs = (
            detect_fvgs(
                candles=candles,
                atr=atr,
                timeframe=timeframe,
                config=self.config.fvg,
            )
            if self.config.enable_fvg_detection
            else []
        )
        for fvg in fvgs:
            log.info(
                "FVG_DETECTED timeframe={} type={} low={} high={} status={} age_bars={} confidence={}",
                timeframe,
                fvg.type,
                fvg.low,
                fvg.high,
                fvg.status,
                fvg.age_bars,
                fvg.confidence,
            )

        return build_technical_analysis_result(
            symbol=context.symbol,
            timeframe=timeframe,
            trace_id=str(context.trace_id),
            double_top=double_top,
            double_bottom=double_bottom,
            fvgs=fvgs,
            regime=regime_value,
            sweep_detected=sweep_detected,
            warnings=warnings,
            metadata={
                "candles_count": len(candles),
                "atr": atr,
                "mode": "pattern_evaluation",
                "timeframe": timeframe,
            },
        )

    @staticmethod
    def _merge_strategy_hints(primary: list[str], additional: list[str]) -> list[str]:
        seen: set[str] = set()
        merged = [*primary, *additional]
        return [hint for hint in merged if not (hint in seen or seen.add(hint))]

    def _apply_multi_timeframe_confirmation(
        self,
        *,
        primary: TechnicalAnalysisResult,
        htf_results: list[TechnicalAnalysisResult],
    ) -> TechnicalAnalysisResult:
        if not htf_results:
            return primary

        htf_buy_avg = sum(result.buy_score for result in htf_results) / len(htf_results)
        htf_sell_avg = sum(result.sell_score for result in htf_results) / len(htf_results)

        weight = clamp_score(self.config.htf_score_weight)
        primary.buy_score = clamp_score((primary.buy_score * (1.0 - weight)) + (htf_buy_avg * weight))
        primary.sell_score = clamp_score((primary.sell_score * (1.0 - weight)) + (htf_sell_avg * weight))

        if (primary.buy_score - primary.sell_score) >= 0.12:
            primary.bias = "buy"
        elif (primary.sell_score - primary.buy_score) >= 0.12:
            primary.bias = "sell"
        else:
            primary.bias = "neutral"

        primary.technical_score = clamp_score(max(primary.buy_score, primary.sell_score) - (0.01 * len(primary.warnings)))

        htf_hints: list[str] = []
        for result in htf_results:
            htf_hints.extend(result.strategy_hints)
        primary.strategy_hints = self._merge_strategy_hints(primary.strategy_hints, htf_hints)

        return primary

    @staticmethod
    def _estimate_atr(candles: list[dict[str, Any]], fallback: float = 1.0) -> float:
        if len(candles) < 2:
            return fallback
        ranges: list[float] = []
        for row in candles[-14:]:
            high = float(row.get("high", 0.0))
            low = float(row.get("low", 0.0))
            if high <= 0 and low <= 0:
                continue
            ranges.append(abs(high - low))
        if not ranges:
            return fallback
        return max(1e-8, sum(ranges) / len(ranges))

    def _neutral_result(
        self,
        context: TradingContext,
        warnings: list[str],
        evidence: list[PatternEvidence] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TechnicalAnalysisResult:
        evidence_list = evidence or []
        return TechnicalAnalysisResult(
            symbol=context.symbol,
            timeframe=context.timeframe,
            bias="neutral",
            technical_score=compute_technical_score("neutral", evidence_list, warnings),
            pattern_evidence=evidence_list,
            warnings=warnings,
            metadata=metadata or {},
            analyzed_at=datetime.now(timezone.utc),
        )

    def run(self, context: TradingContext) -> TradingContext:
        log = logger.bind(trace_id=str(context.trace_id), engine=self.name)
        log.info("TECHNICAL_ANALYSIS_STARTED")

        try:
            if not self.config.enabled:
                context.technical_analysis = self._neutral_result(
                    context=context,
                    warnings=["TECHNICAL_ANALYSIS_DISABLED"],
                    metadata={
                        "trace_id": str(context.trace_id),
                        "mode": "disabled",
                    },
                )
                log.info("TECHNICAL_ANALYSIS_COMPLETED bias={} score={} warnings={}", context.technical_analysis.bias, context.technical_analysis.technical_score, context.technical_analysis.warnings)
                return context

            candles = self._extract_candles(context=context, timeframe=context.timeframe)
            if len(candles) < self.config.min_candles_required:
                context.technical_analysis = self._neutral_result(
                    context=context,
                    warnings=[
                        "TECHNICAL_DATA_INSUFFICIENT",
                    ],
                    metadata={
                        "trace_id": str(context.trace_id),
                        "candles_count": len(candles),
                        "min_candles_required": self.config.min_candles_required,
                        "mode": "safe_neutral",
                    },
                )
            else:
                regime_atr = None
                if context.regime_result is not None:
                    regime_atr = context.regime_result.features.get("atr")
                atr = float(regime_atr) if regime_atr not in (None, 0, 0.0) else self._estimate_atr(candles)
                regime_value = context.regime_result.regime.value if context.regime_result is not None else None
                sweep_detected = bool(
                    ((context.regime_result.features if context.regime_result else {}) or {}).get("liquidity_sweep_detected", False)
                )
                primary_result = self._analyze_timeframe(
                    context=context,
                    timeframe=context.timeframe,
                    candles=candles,
                    atr=atr,
                    regime_value=regime_value,
                    sweep_detected=sweep_detected,
                    log=log,
                )

                htf_results: list[TechnicalAnalysisResult] = []
                htf_warnings: list[str] = []
                if self.config.enable_multi_timeframe:
                    rates_by_timeframe = ((context.ingestion_result or {}).get("rates_by_timeframe") or {})
                    for tf in self.config.confirmation_timeframes:
                        if tf == context.timeframe:
                            continue
                        if tf not in rates_by_timeframe:
                            continue
                        htf_candles = self._extract_candles(context=context, timeframe=tf)
                        if len(htf_candles) < self.config.min_candles_required:
                            htf_warnings.append(f"HTF_{tf}_INSUFFICIENT_DATA")
                            continue

                        htf_atr = self._estimate_atr(htf_candles, fallback=atr)
                        htf_result = self._analyze_timeframe(
                            context=context,
                            timeframe=tf,
                            candles=htf_candles,
                            atr=htf_atr,
                            regime_value=regime_value,
                            sweep_detected=sweep_detected,
                            log=log,
                        )
                        htf_results.append(htf_result)

                merged_result = self._apply_multi_timeframe_confirmation(primary=primary_result, htf_results=htf_results)
                merged_result.warnings.extend(htf_warnings)

                htf_metadata = [
                    {
                        "timeframe": result.timeframe,
                        "bias": result.bias,
                        "technical_score": result.technical_score,
                        "buy_score": result.buy_score,
                        "sell_score": result.sell_score,
                        "warnings": list(result.warnings),
                        "strategy_hints": list(result.strategy_hints),
                    }
                    for result in htf_results
                ]
                merged_result.metadata.update(
                    {
                        "mtf_enabled": self.config.enable_multi_timeframe,
                        "primary_timeframe": context.timeframe,
                        "confirmation_timeframes": list(self.config.confirmation_timeframes),
                        "confirmation_results": htf_metadata,
                    }
                )
                context.technical_analysis = merged_result
        except Exception as exc:  # pragma: no cover - defensive runtime safety
            log.warning("TECHNICAL_ANALYSIS_FAILED_SAFE_FALLBACK error={}", str(exc))
            context.technical_analysis = self._neutral_result(
                context=context,
                warnings=["TECHNICAL_ANALYSIS_ERROR"],
                metadata={
                    "trace_id": str(context.trace_id),
                    "error_message": str(exc),
                    "mode": "exception_fallback",
                },
            )

        log.info(
            "TECHNICAL_ANALYSIS_COMPLETED bias={} score={} warnings={}",
            context.technical_analysis.bias,
            context.technical_analysis.technical_score,
            context.technical_analysis.warnings,
        )
        return context
