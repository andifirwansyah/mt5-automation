"""Strategy selector engine based on market regime and active strategy configs."""

from __future__ import annotations

import math
import uuid
from typing import Any

from src.domain.enums import MarketRegimeType
from src.domain.models.strategy_selection import StrategySelectionResult
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.rejection_reason import (
    NO_ACTIVE_STRATEGIES,
    NO_STRATEGY_MATCHED_REGIME,
    NO_STRATEGY_PASSED_CONFIG,
    NO_STRATEGY_SELECTED,
    REGIME_NOT_TRADEABLE,
    STRATEGY_SELECTION_CONTEXT_MISSING,
    UNSUPPORTED_REGIME_FOR_STRATEGY,
)
from src.pipeline.trading_context import TradingContext
from src.repositories.strategy_repository import StrategyRepository


class StrategySelector(PipelineStep):
    """Select active strategy according to detected market regime."""

    @property
    def name(self) -> str:
        return "StrategySelector"

    def __init__(
        self,
        strategy_repository: StrategyRepository,
        performance_lookback: int = 30,
        recency_decay: float = 0.85,
        min_weighted_trades: float = 5.0,
    ) -> None:
        self.strategy_repository = strategy_repository
        self.performance_lookback = performance_lookback
        self.recency_decay = recency_decay
        self.min_weighted_trades = min_weighted_trades
        self.win_rate_weight = 0.4
        self.profit_factor_weight = 0.35
        self.expectancy_weight = 0.15
        self.sample_weight = 0.10
        self.profit_factor_cap = 3.0
        self.expectancy_scale = 10.0
        self.sample_confidence_trades = 30.0

    @staticmethod
    def _as_uuid(value: object) -> uuid.UUID | None:
        if isinstance(value, uuid.UUID):
            return value
        if isinstance(value, str) and value:
            try:
                return uuid.UUID(value)
            except ValueError:
                return None
        return None

    def _preferred_code_tokens(self, regime: MarketRegimeType) -> list[str]:
        if regime in (MarketRegimeType.TRENDING_BULLISH, MarketRegimeType.TRENDING_BEARISH):
            return ["EMA_ATR_TREND", "TREND"]
        if regime == MarketRegimeType.RANGING:
            return ["RANGE_REVERSION", "REVERSION", "MEAN_REVERSION"]
        if regime == MarketRegimeType.HIGH_VOLATILITY:
            # Keep VOLATILITY_BREAKOUT as primary; LIQUIDITY_SWEEP_REVERSAL as secondary.
            return [
                "VOLATILITY_BREAKOUT",
                "LIQUIDITY_SWEEP_REVERSAL",
                "BREAKOUT",
                "LIQUIDITY",
                "SWEEP",
                "REVERSAL",
            ]
        return []

    @staticmethod
    def _ranked_candidates(strategies: list, preferred_tokens: list[str]) -> list:
        ranked: list = []
        seen_ids: set[str] = set()
        for token in preferred_tokens:
            token_upper = token.upper()
            for strategy in strategies:
                sid = str(strategy.id)
                if sid in seen_ids:
                    continue
                if token_upper in strategy.code.upper():
                    ranked.append(strategy)
                    seen_ids.add(sid)
        return ranked

    @staticmethod
    def _matches_scope(details: dict[str, Any], symbol_id: uuid.UUID, timeframe_id: uuid.UUID) -> bool:
        symbol_scope = details.get("symbol_id")
        timeframe_scope = details.get("timeframe_id")

        if symbol_scope is not None and str(symbol_scope) != str(symbol_id):
            return False
        if timeframe_scope is not None and str(timeframe_scope) != str(timeframe_id):
            return False
        return True

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    def _recent_performance_rows(self, strategy_id: uuid.UUID) -> list[Any]:
        getter = getattr(self.strategy_repository, "get_recent_performance_by_strategy", None)
        if not callable(getter):
            return []
        return list(getter(strategy_id=strategy_id, limit=self.performance_lookback) or [])

    def _weighted_performance_score(
        self,
        strategy_id: uuid.UUID,
        symbol_id: uuid.UUID,
        timeframe_id: uuid.UUID,
    ) -> tuple[float, dict[str, float | int]] | None:
        rows = self._recent_performance_rows(strategy_id)
        scoped_rows: list[Any] = []
        for row in rows:
            details = row.details or {}
            if not isinstance(details, dict):
                details = {}
            if self._matches_scope(details=details, symbol_id=symbol_id, timeframe_id=timeframe_id):
                scoped_rows.append(row)

        if not scoped_rows:
            return None

        weighted_score_sum = 0.0
        weighted_trades_sum = 0.0
        total_weight = 0.0

        for idx, row in enumerate(scoped_rows):
            weight = self.recency_decay**idx
            total_weight += weight

            total_trades = max(0.0, float(row.total_trades or 0))
            win_rate = self._clamp(float(row.win_rate or 0.0), 0.0, 1.0)
            profit_factor = max(0.0, float(row.profit_factor or 0.0))
            pf_norm = self._clamp(profit_factor, 0.0, self.profit_factor_cap) / self.profit_factor_cap

            expectancy = float(row.net_profit or 0.0) / max(total_trades, 1.0)
            expectancy_norm = (math.tanh(expectancy / self.expectancy_scale) + 1.0) / 2.0
            sample_norm = min(1.0, total_trades / self.sample_confidence_trades)

            row_score = (
                (self.win_rate_weight * win_rate)
                + (self.profit_factor_weight * pf_norm)
                + (self.expectancy_weight * expectancy_norm)
                + (self.sample_weight * sample_norm)
            )

            weighted_score_sum += row_score * weight
            weighted_trades_sum += total_trades * weight

        if total_weight <= 0:
            return None

        weighted_trades = weighted_trades_sum / total_weight
        if weighted_trades < self.min_weighted_trades:
            return None

        score = weighted_score_sum / total_weight
        diagnostics: dict[str, float | int] = {
            "score": round(score, 6),
            "records_considered": len(scoped_rows),
            "weighted_trades": round(weighted_trades, 4),
        }
        return score, diagnostics

    def run(self, context: TradingContext) -> TradingContext:
        if context.regime_result is None:
            context.reject("NO_REGIME_RESULT", {"message": "regime_result is required before strategy selection"})
            return context

        regime = context.regime_result.regime
        if not bool(context.regime_result.is_tradeable):
            context.reject(
                context.regime_result.reason or REGIME_NOT_TRADEABLE,
                {
                    "message": "Regime is not tradeable",
                    "regime": regime.value,
                    "confidence": context.regime_result.confidence,
                    "features": context.regime_result.features,
                    "regime_reason": context.regime_result.reason,
                },
            )
            return context

        symbol_id = self._as_uuid((context.ingestion_result or {}).get("symbol_id"))
        timeframe_id = self._as_uuid(((context.ingestion_result or {}).get("timeframe_ids") or {}).get(context.timeframe))
        if symbol_id is None or timeframe_id is None:
            context.reject(
                STRATEGY_SELECTION_CONTEXT_MISSING,
                {
                    "message": "symbol/timeframe references missing in ingestion result",
                    "regime": regime.value,
                    "confidence": context.regime_result.confidence,
                    "features": context.regime_result.features,
                    "ingestion_keys": list((context.ingestion_result or {}).keys()),
                },
            )
            return context

        strategies = self.strategy_repository.get_active_strategies()
        if not strategies:
            context.reject(
                NO_ACTIVE_STRATEGIES,
                {
                    "message": "No active strategies found",
                    "regime": regime.value,
                    "confidence": context.regime_result.confidence,
                    "features": context.regime_result.features,
                },
            )
            return context

        preferred_tokens = self._preferred_code_tokens(regime)
        if not preferred_tokens:
            context.reject(
                UNSUPPORTED_REGIME_FOR_STRATEGY,
                {
                    "message": "Regime has no strategy token mapping",
                    "regime": regime.value,
                    "confidence": context.regime_result.confidence,
                    "features": context.regime_result.features,
                    "active_strategy_codes": [s.code for s in strategies],
                },
            )
            return context

        candidates = self._ranked_candidates(strategies=strategies, preferred_tokens=preferred_tokens)
        if not candidates:
            context.reject(
                NO_STRATEGY_MATCHED_REGIME,
                {
                    "message": "No active strategy matched regime",
                    "regime": regime.value,
                    "preferred_tokens": preferred_tokens,
                    "active_strategy_codes": [s.code for s in strategies],
                    "confidence": context.regime_result.confidence,
                    "features": context.regime_result.features,
                },
            )
            return context

        selected = None
        selected_config = {}
        rejected_candidates: list[dict[str, str]] = []
        eligible_candidates: list[tuple[Any, dict[str, Any]]] = []
        for strategy in candidates:
            configs = self.strategy_repository.get_active_strategy_configs(
                strategy_id=strategy.id,
                symbol_id=symbol_id,
                timeframe_id=timeframe_id,
            )
            config_payload = configs[0].config if configs else {}

            if regime == MarketRegimeType.HIGH_VOLATILITY and not bool(config_payload.get("allow_high_volatility", True)):
                rejected_candidates.append({"strategy_code": strategy.code, "reason": "HIGH_VOLATILITY_DISABLED_BY_CONFIG"})
                continue

            eligible_candidates.append((strategy, config_payload))

        if not eligible_candidates:
            context.reject(
                NO_STRATEGY_PASSED_CONFIG,
                {
                    "message": "No strategy passed config constraints",
                    "regime": regime.value,
                    "preferred_tokens": preferred_tokens,
                    "candidate_strategy_codes": [s.code for s in candidates],
                    "rejected_candidates": rejected_candidates,
                    "confidence": context.regime_result.confidence,
                    "features": context.regime_result.features,
                },
            )
            return context

        ranking_details: list[dict[str, Any]] = []
        ranked_by_weighted_performance: list[tuple[float, Any, dict[str, Any], dict[str, float | int]]] = []
        for idx, (strategy, config_payload) in enumerate(eligible_candidates):
            perf_result = self._weighted_performance_score(
                strategy_id=strategy.id,
                symbol_id=symbol_id,
                timeframe_id=timeframe_id,
            )
            if perf_result is None:
                ranking_details.append(
                    {
                        "strategy_code": strategy.code,
                        "eligible_order": idx,
                        "score": None,
                        "scoring": "fallback_no_performance_data",
                    }
                )
                continue
            score, diagnostics = perf_result
            ranked_by_weighted_performance.append((score, strategy, config_payload, diagnostics))
            ranking_details.append(
                {
                    "strategy_code": strategy.code,
                    "eligible_order": idx,
                    "score": diagnostics["score"],
                    "weighted_trades": diagnostics["weighted_trades"],
                    "records_considered": diagnostics["records_considered"],
                    "scoring": "weighted_performance",
                }
            )

        if ranked_by_weighted_performance:
            ranked_by_weighted_performance.sort(
                key=lambda item: (
                    item[0],
                    -next(i for i, (s, _) in enumerate(eligible_candidates) if s.id == item[1].id),
                ),
                reverse=True,
            )
            _, selected, selected_config, selected_diag = ranked_by_weighted_performance[0]
            selection_reason = f"Weighted performance winner for regime={regime.value}"
            selection_details: dict[str, Any] = {
                "regime": regime.value,
                "config": selected_config,
                "selector_mode": "weighted_performance",
                "weighted_score": selected_diag["score"],
                "weighted_trades": selected_diag["weighted_trades"],
                "ranking": ranking_details,
            }
        else:
            selected, selected_config = eligible_candidates[0]
            selection_reason = f"Matched by regime={regime.value}"
            selection_details = {
                "regime": regime.value,
                "config": selected_config,
                "selector_mode": "fallback_token_order",
                "ranking": ranking_details,
            }

        self.strategy_repository.create_strategy_selection(
            trace_id=context.trace_id,
            symbol_id=symbol_id,
            timeframe_id=timeframe_id,
            strategy_id=selected.id,
            score=round(float(context.regime_result.confidence), 4),
            reason=selection_reason,
            details=selection_details,
        )
        self.strategy_repository.session.commit()

        context.strategy_selection = StrategySelectionResult(
            strategy_code=selected.code,
            strategy_name=selected.name,
            score=float(context.regime_result.confidence),
            reason=selection_reason,
            config=selected_config,
            details={
                "strategy_id": str(selected.id),
                "selector_mode": selection_details["selector_mode"],
                "ranking": ranking_details,
            },
        )

        # Generic fallback should remain available, but not for no-trade regimes.
        if context.strategy_selection.strategy_code == "":
            context.reject(NO_STRATEGY_SELECTED, {"message": "Unexpected empty strategy code"})
        return context
