"""MT5 order execution adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.config.settings import AppSettings, get_settings
from src.domain.enums import OrderExecutionStatus, SignalDirection
from src.domain.models.execution_decision import ExecutionDecision
from src.domain.models.order_result import OrderResult
from src.domain.models.risk_plan import RiskPlan
from src.domain.models.signal import SignalContract

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover
    mt5 = None  # type: ignore[assignment]


class MT5OrderExecutor:
    """Adapter for order_check and market order execution in MT5."""

    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or get_settings()

    @staticmethod
    def _require_mt5() -> None:
        if mt5 is None:
            raise RuntimeError("MetaTrader5 package is not available in this environment.")

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def order_check(self, request: dict[str, Any]) -> dict[str, Any] | None:
        self._require_mt5()
        result = mt5.order_check(request)
        return result._asdict() if result is not None else None

    def build_market_order_request(self, signal: SignalContract, risk_plan: RiskPlan) -> dict[str, Any]:
        self._require_mt5()

        sl = float(risk_plan.stop_loss or signal.stop_loss)
        tp = float(risk_plan.take_profit or signal.take_profit)
        lot = float(risk_plan.lot_size or signal.lot_size)

        if sl <= 0 or tp <= 0:
            raise ValueError("SL and TP are required and must be > 0.")
        if lot <= 0:
            raise ValueError("Lot size must be > 0.")
        if not signal.symbol:
            raise ValueError("Symbol is required.")

        tick = mt5.symbol_info_tick(signal.symbol)
        if tick is None:
            raise ValueError(f"Failed to get symbol tick for {signal.symbol}.")

        if signal.direction == SignalDirection.BUY:
            order_type = mt5.ORDER_TYPE_BUY
            price = float(getattr(tick, "ask", signal.entry_price))
        elif signal.direction == SignalDirection.SELL:
            order_type = mt5.ORDER_TYPE_SELL
            price = float(getattr(tick, "bid", signal.entry_price))
        else:
            raise ValueError("Only BUY/SELL signals can be executed.")

        return {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": signal.symbol,
            "volume": lot,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": self.settings.order_deviation,
            "magic": self.settings.trading_magic_number,
            "comment": f"ai-trading:{signal.strategy_code}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

    def send_market_order(self, signal: SignalContract, risk_plan: RiskPlan, decision: ExecutionDecision) -> OrderResult:
        if self.settings.dry_run:
            request = self.build_market_order_request(signal=signal, risk_plan=risk_plan)
            return OrderResult(
                status=OrderExecutionStatus.DRY_RUN,
                dry_run=True,
                submitted_at=self._now(),
                request_payload=request,
                response_payload={"message": "DRY_RUN active. order_send skipped."},
            )

        if not decision.approved:
            return OrderResult(
                status=OrderExecutionStatus.REJECTED,
                dry_run=False,
                submitted_at=self._now(),
                error_message=f"Execution decision rejected: {decision.reason}",
            )

        try:
            self._require_mt5()
            request = self.build_market_order_request(signal=signal, risk_plan=risk_plan)
        except Exception as exc:
            return OrderResult(
                status=OrderExecutionStatus.ERROR,
                dry_run=False,
                submitted_at=self._now(),
                error_message=str(exc),
            )

        check_result = self.order_check(request)
        if check_result is None:
            return OrderResult(
                status=OrderExecutionStatus.ERROR,
                dry_run=False,
                submitted_at=self._now(),
                request_payload=request,
                error_message="order_check returned None.",
            )

        check_retcode = int(check_result.get("retcode", -1))
        if check_retcode != getattr(mt5, "TRADE_RETCODE_DONE", 0):
            return OrderResult(
                status=OrderExecutionStatus.REJECTED,
                dry_run=False,
                submitted_at=self._now(),
                request_payload=request,
                response_payload=check_result,
                error_message=f"order_check rejected with retcode={check_retcode}",
            )

        result = mt5.order_send(request)
        if result is None:
            return OrderResult(
                status=OrderExecutionStatus.ERROR,
                dry_run=False,
                submitted_at=self._now(),
                request_payload=request,
                error_message=f"order_send failed: {mt5.last_error()}",
            )

        result_dict = result._asdict()
        retcode = int(result_dict.get("retcode", -1))

        success_codes = {
            getattr(mt5, "TRADE_RETCODE_DONE", 0),
            getattr(mt5, "TRADE_RETCODE_PLACED", 10008),
        }
        if retcode in success_codes:
            return OrderResult(
                status=OrderExecutionStatus.FILLED,
                dry_run=False,
                submitted_at=self._now(),
                order_ticket=int(result_dict.get("order", 0) or 0),
                request_payload=request,
                response_payload=result_dict,
            )

        return OrderResult(
            status=OrderExecutionStatus.REJECTED,
            dry_run=False,
            submitted_at=self._now(),
            request_payload=request,
            response_payload=result_dict,
            error_message=f"order_send rejected with retcode={retcode}",
        )
