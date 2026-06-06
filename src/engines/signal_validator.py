"""Signal validator engine."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from src.config.settings import AppSettings, get_settings
from src.domain.enums import MarketRegimeType, SignalDirection, ValidationStatus
from src.domain.models.validation_result import ValidationResult
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.rejection_reason import (
    BAD_MARKET_STRUCTURE_LOCATION,
    BUY_TOO_CLOSE_TO_RESISTANCE,
    INSUFFICIENT_ROOM_TO_TARGET_ZONE,
    MARKET_STRUCTURE_CONFLICT,
    MARKET_STRUCTURE_MISSING,
    MARKET_STRUCTURE_UNRELIABLE,
    PRICE_IN_NO_TRADE_ZONE,
    SELL_TOO_CLOSE_TO_SUPPORT,
)
from src.pipeline.trading_context import TradingContext
from src.repositories.position_repository import PositionRepository
from src.repositories.signal_repository import SignalRepository


class SignalValidator(PipelineStep):
    """Validate normalized signal contract before edge/risk stages."""

    @property
    def name(self) -> str:
        return "SignalValidator"

    def __init__(self, signal_repository: SignalRepository, position_repository: PositionRepository, settings: AppSettings | None = None) -> None:
        self.signal_repository = signal_repository
        self.position_repository = position_repository
        self.settings = settings or get_settings()

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

    def _is_regime_strategy_compatible(self, regime: MarketRegimeType, strategy_code: str) -> bool:
        code = strategy_code.upper()
        if regime in (MarketRegimeType.TRENDING_BULLISH, MarketRegimeType.TRENDING_BEARISH):
            return "TREND" in code
        if regime == MarketRegimeType.RANGING:
            return "REVERSION" in code or "RANGE" in code
        if regime == MarketRegimeType.HIGH_VOLATILITY:
            return ("BREAKOUT" in code) or ("LIQUIDITY" in code) or ("SWEEP" in code)
        if regime == MarketRegimeType.CHOPPY:
            return False
        return True

    def _validate_market_structure_location(self, context: TradingContext) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Validate signal location without making structure a blind absolute blocker."""

        structure = context.market_structure
        contract = context.signal_contract
        if contract is None:
            return [], []

        if structure is None:
            return [
                {
                    "check": MARKET_STRUCTURE_MISSING,
                    "message": "market_structure is required before signal validation",
                }
            ], []

        structure_mode = str((structure.metadata or {}).get("mode", "")).upper()
        structure_reason = str((structure.metadata or {}).get("reason", "")).upper()
        if structure_mode == "SAFE_UNCLEAR" or structure_reason in {
            "MARKET_STRUCTURE_DATA_INSUFFICIENT",
            "MARKET_STRUCTURE_ERROR",
            "MARKET_STRUCTURE_DISABLED",
        }:
            return [
                {
                    "check": MARKET_STRUCTURE_UNRELIABLE,
                    "message": "market_structure is not reliable enough for signal validation",
                    "mode": structure_mode,
                    "reason": structure_reason,
                    "structure": structure.to_summary(),
                }
            ], []

        issues: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        direction = contract.direction
        entry_price = float(contract.entry_price)
        confidence = float(getattr(contract, "confidence", 0.0) or 0.0)
        override_confidence = float(getattr(self.settings, "market_structure_override_min_confidence", 0.70))
        allow_confidence_override = confidence >= override_confidence
        atr = max(1e-8, float(structure.atr or 1.0))
        min_room_factor = float((structure.metadata or {}).get("minimum_room_to_zone_atr", 0.80) or 0.80)
        soft_min_room = atr * min_room_factor
        hard_min_room_factor = float(getattr(self.settings, "market_structure_hard_min_room_atr", 0.30))
        hard_min_room = atr * hard_min_room_factor
        zone_tolerance_factor = float((structure.metadata or {}).get("zone_tolerance_atr", 0.45) or 0.45)
        zone_tolerance = atr * zone_tolerance_factor
        danger_distance = atr * float((structure.metadata or {}).get("danger_zone_atr", 0.55) or 0.55)

        entry_distance_to_support = abs(entry_price - float(structure.nearest_support)) if structure.nearest_support is not None else None
        entry_distance_to_resistance = abs(float(structure.nearest_resistance) - entry_price) if structure.nearest_resistance is not None else None
        entry_near_support = any(zone.contains(entry_price) for zone in structure.support_zones) or (
            entry_distance_to_support is not None and entry_distance_to_support <= zone_tolerance
        )
        entry_near_resistance = any(zone.contains(entry_price) for zone in structure.resistance_zones) or (
            entry_distance_to_resistance is not None and entry_distance_to_resistance <= zone_tolerance
        )
        entry_too_close_to_support = entry_distance_to_support is not None and entry_distance_to_support <= danger_distance
        entry_too_close_to_resistance = entry_distance_to_resistance is not None and entry_distance_to_resistance <= danger_distance
        entry_valid_buy_zone = structure.valid_buy_zone and not entry_near_resistance
        entry_valid_sell_zone = structure.valid_sell_zone and not entry_near_support

        def add_soft_or_hard(item: dict[str, Any]) -> None:
            item = {
                **item,
                "confidence": confidence,
                "override_min_confidence": override_confidence,
                "soft_structure_rule": True,
            }
            if allow_confidence_override:
                warnings.append(item)
            else:
                issues.append(item)

        if direction == SignalDirection.BUY:
            if not entry_valid_buy_zone:
                add_soft_or_hard(
                    {
                        "check": BAD_MARKET_STRUCTURE_LOCATION,
                        "message": "BUY signal entry is not located in a valid buy structure zone",
                        "structure": structure.to_summary(),
                        "entry_near_support": entry_near_support,
                        "entry_near_resistance": entry_near_resistance,
                    }
                )
            if entry_too_close_to_resistance:
                issues.append(
                    {
                        "check": BUY_TOO_CLOSE_TO_RESISTANCE,
                        "message": "BUY signal is too close to nearest resistance",
                        "nearest_resistance": structure.nearest_resistance,
                        "entry_price": entry_price,
                    }
                )
            if structure.nearest_resistance is not None:
                room = float(structure.nearest_resistance) - entry_price
                if room <= 0 or room < hard_min_room:
                    issues.append(
                        {
                            "check": INSUFFICIENT_ROOM_TO_TARGET_ZONE,
                            "message": "BUY signal has critically insufficient room before nearest resistance",
                            "room_to_resistance": room,
                            "minimum_room": hard_min_room,
                            "nearest_resistance": structure.nearest_resistance,
                        }
                    )
                elif room < soft_min_room:
                    add_soft_or_hard(
                        {
                            "check": INSUFFICIENT_ROOM_TO_TARGET_ZONE,
                            "message": "BUY signal has limited room before nearest resistance",
                            "room_to_resistance": room,
                            "minimum_room": soft_min_room,
                            "nearest_resistance": structure.nearest_resistance,
                        }
                    )
            if structure.trend_structure == "BEARISH" and not entry_near_support:
                add_soft_or_hard(
                    {
                        "check": MARKET_STRUCTURE_CONFLICT,
                        "message": "BUY signal conflicts with bearish market structure away from support",
                        "trend_structure": structure.trend_structure,
                    }
                )

        if direction == SignalDirection.SELL:
            if not entry_valid_sell_zone:
                add_soft_or_hard(
                    {
                        "check": BAD_MARKET_STRUCTURE_LOCATION,
                        "message": "SELL signal entry is not located in a valid sell structure zone",
                        "structure": structure.to_summary(),
                        "entry_near_support": entry_near_support,
                        "entry_near_resistance": entry_near_resistance,
                    }
                )
            if entry_too_close_to_support:
                issues.append(
                    {
                        "check": SELL_TOO_CLOSE_TO_SUPPORT,
                        "message": "SELL signal is too close to nearest support",
                        "nearest_support": structure.nearest_support,
                        "entry_price": entry_price,
                    }
                )
            if structure.nearest_support is not None:
                room = entry_price - float(structure.nearest_support)
                if room <= 0 or room < hard_min_room:
                    issues.append(
                        {
                            "check": INSUFFICIENT_ROOM_TO_TARGET_ZONE,
                            "message": "SELL signal has critically insufficient room before nearest support",
                            "room_to_support": room,
                            "minimum_room": hard_min_room,
                            "nearest_support": structure.nearest_support,
                        }
                    )
                elif room < soft_min_room:
                    add_soft_or_hard(
                        {
                            "check": INSUFFICIENT_ROOM_TO_TARGET_ZONE,
                            "message": "SELL signal has limited room before nearest support",
                            "room_to_support": room,
                            "minimum_room": soft_min_room,
                            "nearest_support": structure.nearest_support,
                        }
                    )
            if structure.trend_structure == "BULLISH" and not entry_near_resistance:
                add_soft_or_hard(
                    {
                        "check": MARKET_STRUCTURE_CONFLICT,
                        "message": "SELL signal conflicts with bullish market structure away from resistance",
                        "trend_structure": structure.trend_structure,
                    }
                )

        if not structure.valid_buy_zone and not structure.valid_sell_zone:
            add_soft_or_hard(
                {
                    "check": PRICE_IN_NO_TRADE_ZONE,
                    "message": "Current price is not near actionable support/resistance structure",
                    "structure": structure.to_summary(),
                }
            )

        return issues, warnings

    def run(self, context: TradingContext) -> TradingContext:
        if context.signal_contract is None:
            context.reject("SIGNAL_VALIDATION_FAILED", {"message": "signal_contract missing"})
            return context

        contract = context.signal_contract
        issues: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []

        if contract.direction not in (SignalDirection.BUY, SignalDirection.SELL):
            issues.append({"check": "SIDE_VALID", "message": f"Invalid side={contract.direction}"})

        if contract.entry_price <= 0:
            issues.append({"check": "ENTRY_PRICE_VALID", "message": "entry_price must be > 0"})

        if contract.stop_loss <= 0 or contract.take_profit <= 0:
            issues.append({"check": "SL_TP_PRESENT", "message": "stop_loss and take_profit must be > 0"})
        elif contract.direction == SignalDirection.BUY:
            if not (contract.stop_loss < contract.entry_price < contract.take_profit):
                issues.append(
                    {
                        "check": "SL_TP_DIRECTION_VALID",
                        "message": "BUY requires stop_loss < entry_price < take_profit",
                        "entry_price": contract.entry_price,
                        "stop_loss": contract.stop_loss,
                        "take_profit": contract.take_profit,
                    }
                )
        elif contract.direction == SignalDirection.SELL:
            if not (contract.take_profit < contract.entry_price < contract.stop_loss):
                issues.append(
                    {
                        "check": "SL_TP_DIRECTION_VALID",
                        "message": "SELL requires take_profit < entry_price < stop_loss",
                        "entry_price": contract.entry_price,
                        "stop_loss": contract.stop_loss,
                        "take_profit": contract.take_profit,
                    }
                )

        ingestion = context.ingestion_result or {}
        symbol_id = self._as_uuid(ingestion.get("symbol_id"))
        timeframe_id = self._as_uuid((ingestion.get("timeframe_ids") or {}).get(context.timeframe))
        signal_id = self._as_uuid(contract.metadata.get("signal_id"))

        if symbol_id and timeframe_id:
            duplicate_count = self.signal_repository.count_signals_by_candle(
                symbol_id=symbol_id,
                timeframe_id=timeframe_id,
                signal_time=contract.generated_at,
                exclude_signal_id=signal_id,
            )
            if duplicate_count > 0:
                issues.append({"check": "DUPLICATE_SIGNAL", "message": f"duplicate_count={duplicate_count}"})

        if context.regime_result is not None:
            if context.regime_result.regime == MarketRegimeType.CHOPPY:
                issues.append({"check": "REGIME_TRADE_ALLOWED", "message": "CHOPPY regime must not trade"})
            if not self._is_regime_strategy_compatible(context.regime_result.regime, contract.strategy_code):
                issues.append(
                    {
                        "check": "REGIME_STRATEGY_MATCH",
                        "message": f"strategy={contract.strategy_code} incompatible with regime={context.regime_result.regime.value}",
                    }
                )

            mtf_policy = ((context.regime_result.features or {}).get("mtf_policy") or {})
            if isinstance(mtf_policy, dict) and bool(mtf_policy.get("enabled", False)):
                allowed_directions = [str(direction).upper() for direction in (mtf_policy.get("allowed_directions") or [])]
                side = contract.direction.value.upper()
                if allowed_directions and side not in allowed_directions:
                    issues.append(
                        {
                            "check": "MTF_POLICY_DIRECTION",
                            "message": f"direction={side} not allowed by mtf_policy={allowed_directions}",
                            "policy": mtf_policy,
                        }
                    )

        spread = context.market_snapshot.spread if context.market_snapshot else None
        if spread is not None and float(spread) > float(self.settings.max_spread):
            issues.append({"check": "SPREAD_LIMIT", "message": f"spread={spread} > max_spread={self.settings.max_spread}"})

        if symbol_id is not None:
            open_positions = self.position_repository.get_open_positions(symbol_id=symbol_id)
            if len(open_positions) >= int(self.settings.max_open_positions_per_symbol):
                issues.append(
                    {
                        "check": "OPEN_POSITION_LIMIT",
                        "message": f"open_positions={len(open_positions)} >= limit={self.settings.max_open_positions_per_symbol}",
                    }
                )

        structure_issues, structure_warnings = self._validate_market_structure_location(context)
        issues.extend(structure_issues)
        warnings.extend(structure_warnings)

        technical_summary = contract.metadata.get("technical_summary") if isinstance(contract.metadata, dict) else {}
        if isinstance(technical_summary, dict):
            technical_bias = str(technical_summary.get("technical_bias", "neutral")).lower()
            buy_score = float(technical_summary.get("buy_score", 0.0) or 0.0)
            sell_score = float(technical_summary.get("sell_score", 0.0) or 0.0)
            direction = contract.direction.value.lower()

            conflict = (direction == "buy" and technical_bias == "sell") or (direction == "sell" and technical_bias == "buy")
            if conflict:
                severity = abs(buy_score - sell_score)
                warning_item = {
                    "check": "TECHNICAL_CONFLICT",
                    "message": f"signal={direction} conflicts technical_bias={technical_bias}",
                    "severity": severity,
                    "setup_signature": technical_summary.get("setup_signature"),
                }
                warnings.append(warning_item)

                policy = (context.strategy_selection.config.get("technical_validation") if context.strategy_selection else None) or {}
                hard_reject_enabled = bool(policy.get("hard_reject_on_severe_conflict", False))
                severe_threshold = float(policy.get("severe_conflict_threshold", 0.30))
                if hard_reject_enabled and severity >= severe_threshold:
                    issues.append({**warning_item, "check": "TECHNICAL_CONFLICT_SEVERE"})

        validated_at = datetime.now(timezone.utc)
        if issues:
            self.signal_repository.create_signal_validation(
                signal_id=signal_id,
                validator_name="SignalValidator",
                status="REJECTED",
                validated_at=validated_at,
                rejection_reason="SIGNAL_VALIDATION_FAILED",
                details={"issues": issues, "warnings": warnings},
            )
            self.signal_repository.session.commit()

            context.signal_validation = ValidationResult(
                status=ValidationStatus.REJECTED,
                reason="SIGNAL_VALIDATION_FAILED",
                validator_name="SignalValidator",
                details={"issues": issues, "warnings": warnings},
            )
            context.reject("SIGNAL_VALIDATION_FAILED", {"issues": issues})
            return context

        self.signal_repository.create_signal_validation(
            signal_id=signal_id,
            validator_name="SignalValidator",
            status="PASSED",
            validated_at=validated_at,
            rejection_reason=None,
            details={"message": "Signal validation passed", "warnings": warnings},
        )
        self.signal_repository.session.commit()

        context.signal_validation = ValidationResult(
            status=ValidationStatus.PASSED,
            reason=None,
            validator_name="SignalValidator",
            details={"issues": [], "warnings": warnings},
        )
        return context
