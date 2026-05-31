"""Risk engine for position sizing and SL/TP risk plan generation."""

from __future__ import annotations

import math
import uuid
from typing import Any

from src.config.settings import AppSettings, get_settings
from src.domain.models.risk_plan import RiskPlan
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories.risk_repository import RiskRepository


class RiskEngine(PipelineStep):
    """Compute risk amount, lot size, and validate SL/TP constraints."""

    @property
    def name(self) -> str:
        return "RiskEngine"

    def __init__(self, risk_repository: RiskRepository, settings: AppSettings | None = None) -> None:
        self.risk_repository = risk_repository
        self.settings = settings or get_settings()

    @staticmethod
    def _round_down_to_step(value: float, step: float) -> float:
        if step <= 0:
            return value
        return math.floor(value / step) * step

    def _safe_xau_lot(self, lot: float) -> float:
        return lot * 0.7

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

    def run(self, context: TradingContext) -> TradingContext:
        if context.signal_contract is None:
            context.reject("RISK_FAILED", {"message": "signal_contract missing"})
            return context

        contract = context.signal_contract
        account_info = (context.ingestion_result or {}).get("account_info") or {}
        symbol_info = (context.ingestion_result or {}).get("symbol_info") or {}
        atr = float((context.regime_result.features if context.regime_result else {}).get("atr", 0.0))

        snapshot_features = (context.market_snapshot.features if context.market_snapshot else {}) or {}
        equity = float(snapshot_features.get("account_equity", account_info.get("equity", 0.0)))
        balance = float(snapshot_features.get("account_balance", account_info.get("balance", 0.0)))
        account_base = equity if equity > 0 else balance
        if account_base <= 0:
            context.reject("RISK_FAILED", {"message": "equity/balance unavailable or invalid"})
            return context

        risk_amount = account_base * (float(self.settings.risk_per_trade_percent) / 100.0)
        entry = float(contract.entry_price)
        sl = float(contract.stop_loss)
        tp = float(contract.take_profit)

        if sl <= 0 or tp <= 0:
            if atr <= 0:
                context.reject("RISK_FAILED", {"message": "SL/TP missing and ATR unavailable"})
                return context
            if contract.direction.value == "BUY":
                sl = entry - (1.5 * atr)
                tp = entry + (2.0 * atr)
            else:
                sl = entry + (1.5 * atr)
                tp = entry - (2.0 * atr)

        risk_distance = abs(entry - sl)
        reward_distance = abs(tp - entry)
        if risk_distance <= 0 or reward_distance <= 0:
            context.reject("RISK_FAILED", {"message": "invalid SL/TP distances"})
            return context

        rr_ratio = reward_distance / risk_distance

        volume_min = float(symbol_info.get("volume_min", self.settings.fixed_lot))
        volume_max_broker = float(symbol_info.get("volume_max", self.settings.max_lot))
        volume_step = float(symbol_info.get("volume_step", 0.01))
        volume_max = min(volume_max_broker, float(self.settings.max_lot))
        contract_size = float(symbol_info.get("trade_contract_size", 0.0))

        fallback_to_fixed = False
        fallback_reason = None

        lot_size: float
        if contract_size > 0:
            raw_lot = risk_amount / (risk_distance * contract_size)
            if "XAUUSD" in contract.symbol.upper():
                raw_lot = self._safe_xau_lot(raw_lot)
            lot_size = self._round_down_to_step(raw_lot, volume_step)
            lot_size = max(volume_min, min(volume_max, lot_size))
        else:
            fallback_to_fixed = True
            fallback_reason = "contract_size unavailable, fallback FIXED_LOT"
            lot_size = float(self.settings.fixed_lot)

        if lot_size <= 0:
            context.reject("RISK_FAILED", {"message": "lot size <= 0 after sizing"})
            return context

        details: dict[str, Any] = {
            "equity": equity,
            "balance": balance,
            "account_base": account_base,
            "risk_amount": risk_amount,
            "risk_distance": risk_distance,
            "reward_distance": reward_distance,
            "rr_ratio": rr_ratio,
            "volume_min": volume_min,
            "volume_max": volume_max,
            "volume_step": volume_step,
            "contract_size": contract_size,
            "fallback_to_fixed_lot": fallback_to_fixed,
            "fallback_reason": fallback_reason,
        }

        passed = sl > 0 and tp > 0 and rr_ratio >= float(self.settings.min_rr)
        rejection_reason = None if passed else "RISK_CONSTRAINT_FAILED"

        signal_id = self._as_uuid(contract.metadata.get("signal_id"))
        if signal_id is None:
            context.reject("RISK_FAILED", {"message": "signal_id missing"})
            return context

        self.risk_repository.create_risk_assessment(
            signal_id=signal_id,
            risk_per_trade_pct=float(self.settings.risk_per_trade_percent),
            max_daily_loss_pct=float(account_info.get("max_daily_loss_pct", 0.0)),
            position_size_lot=lot_size,
            stop_loss_pips=risk_distance,
            take_profit_pips=reward_distance,
            risk_reward_ratio=rr_ratio,
            passed=passed,
            assessed_at=context.candle_time,
            rejection_reason=rejection_reason,
            details=details,
        )
        self.risk_repository.session.commit()

        context.risk_plan = RiskPlan(
            passed=passed,
            lot_size=lot_size,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            risk_per_trade_pct=float(self.settings.risk_per_trade_percent),
            max_daily_loss_pct=float(account_info.get("max_daily_loss_pct", 0.0)),
            reason=rejection_reason,
            details=details,
        )

        if not passed:
            context.reject("RISK_FAILED", details)
        return context
