"""Pre-trade simulation engine."""

from __future__ import annotations

import uuid

from src.config.settings import AppSettings, get_settings
from src.domain.models.simulation_result import SimulationResult
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories.risk_repository import RiskRepository


class PreTradeSimulation(PipelineStep):
    """Stress-test signal execution assumptions before execution gate."""

    @property
    def name(self) -> str:
        return "PreTradeSimulation"

    def __init__(self, risk_repository: RiskRepository, settings: AppSettings | None = None) -> None:
        self.risk_repository = risk_repository
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

    def run(self, context: TradingContext) -> TradingContext:
        if context.signal_contract is None or context.risk_plan is None:
            context.reject("PRE_TRADE_SIMULATION_FAILED", {"message": "signal_contract and risk_plan required"})
            return context

        signal = context.signal_contract
        risk_plan = context.risk_plan
        details = risk_plan.details or {}

        spread_now = float(context.market_snapshot.spread) if context.market_snapshot and context.market_snapshot.spread is not None else 0.0
        spread_stress = spread_now * float(self.settings.pretrade_spread_stress_multiplier)

        point = 0.01 if "XAUUSD" in signal.symbol.upper() else 0.0001
        slippage_price = float(self.settings.pretrade_slippage_points) * point

        entry = float(signal.entry_price)
        stop_loss = float(risk_plan.stop_loss)
        take_profit = float(risk_plan.take_profit)
        lot_size = float(risk_plan.lot_size)
        contract_size = float(details.get("contract_size", 100.0))
        risk_amount = float(details.get("risk_amount", 0.0))

        if signal.direction.value == "BUY":
            stressed_entry = entry + spread_stress + slippage_price
            stressed_stop = stop_loss - slippage_price
        else:
            stressed_entry = entry - spread_stress - slippage_price
            stressed_stop = stop_loss + slippage_price

        worst_loss_per_unit = abs(stressed_entry - stressed_stop)
        worst_case_loss = worst_loss_per_unit * contract_size * lot_size

        expected_profit = abs(take_profit - entry) * contract_size * lot_size
        rr_ratio = float(details.get("rr_ratio", 0.0))

        passed = (worst_case_loss <= risk_amount) and (rr_ratio >= float(self.settings.min_rr))
        reason = None if passed else "PRE_TRADE_CONSTRAINT_FAILED"

        simulation_details = {
            "spread_now": spread_now,
            "spread_stress": spread_stress,
            "slippage_price": slippage_price,
            "stressed_entry": stressed_entry,
            "stressed_stop": stressed_stop,
            "worst_loss_per_unit": worst_loss_per_unit,
            "worst_case_loss": worst_case_loss,
            "risk_amount": risk_amount,
            "rr_ratio": rr_ratio,
            "min_rr": float(self.settings.min_rr),
        }

        signal_id = self._as_uuid(signal.metadata.get("signal_id"))
        if signal_id is None:
            context.reject("PRE_TRADE_SIMULATION_FAILED", {"message": "signal_id missing"})
            return context

        self.risk_repository.create_pre_trade_simulation(
            signal_id=signal_id,
            expected_profit=expected_profit,
            expected_drawdown=worst_case_loss,
            slippage_estimate=slippage_price,
            passed=passed,
            simulated_at=context.candle_time,
            rejection_reason=reason,
            details=simulation_details,
        )
        self.risk_repository.session.commit()

        context.simulation_result = SimulationResult(
            passed=passed,
            expected_profit=expected_profit,
            expected_drawdown=worst_case_loss,
            slippage_estimate=slippage_price,
            reason=reason,
            details=simulation_details,
        )

        if not passed:
            context.reject("PRE_TRADE_SIMULATION_FAILED", simulation_details)
        return context
