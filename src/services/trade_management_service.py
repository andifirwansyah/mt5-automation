"""Dynamic trade management: break-even and trailing stop for open positions.

The bot sets a static SL/TP at entry. Without post-entry management, a position
that runs most of the way to TP and then reverses gives back unrealized profit
and can close at a loss. This service locks in progress by moving the stop-loss:

1. Break-even: once price has travelled `breakeven_trigger_ratio` of the way to
   TP, the SL is pushed to entry (+ a small buffer to cover spread/commission),
   so a reversal closes flat instead of at a loss.
2. Trailing: once `trailing_activation_ratio` is reached, the SL trails the
   current price by `trailing_distance_ratio` of the reward leg, locking in more
   profit the further price runs.

The logic is stateless: the "high-water mark" is the position's own live SL in
MT5, since the SL is only ever moved in the favourable direction.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from src.domain.enums import OrderExecutionStatus
from src.infrastructure.mt5.mt5_order_executor import MT5OrderExecutor


@dataclass(frozen=True)
class TradeManagementConfig:
    """Tunable parameters for break-even and trailing-stop management."""

    enabled: bool
    breakeven_trigger_ratio: float
    breakeven_buffer_ratio: float
    trailing_enabled: bool
    trailing_activation_ratio: float
    trailing_distance_ratio: float
    trailing_aggressive_activation_ratio: float
    trailing_aggressive_distance_ratio: float
    min_step_ratio: float


def compute_managed_sl(
    *,
    side: str,
    entry: float,
    take_profit: float,
    current_price: float,
    current_sl: float,
    config: TradeManagementConfig,
    min_stop_distance: float = 0.0,
) -> float | None:
    """Compute the new stop-loss for a position, or ``None`` if no change is needed.

    The returned SL is only ever tightened (moved toward price / into profit) and
    is clamped to respect the broker minimum stop distance and never crosses TP.
    """

    side = side.upper()
    reward = abs(take_profit - entry)
    if reward <= 0 or current_price <= 0 or entry <= 0:
        return None

    if side == "BUY":
        progress = (current_price - entry) / reward
    elif side == "SELL":
        progress = (entry - current_price) / reward
    else:
        return None

    if progress <= 0:
        return None

    breakeven_active = progress >= config.breakeven_trigger_ratio
    trailing_active = config.trailing_enabled and progress >= config.trailing_activation_ratio
    aggressive_trailing_active = config.trailing_enabled and progress >= config.trailing_aggressive_activation_ratio
    if not breakeven_active and not trailing_active:
        return None

    buffer = config.breakeven_buffer_ratio * reward
    trail = config.trailing_distance_ratio * reward
    aggressive_trail = config.trailing_aggressive_distance_ratio * reward
    tolerance = config.min_step_ratio * reward

    if side == "BUY":
        # An unset SL (0.0) must not anchor the candidate; treat it as the worst case.
        candidate = current_sl if current_sl > 0 else float("-inf")
        if breakeven_active:
            candidate = max(candidate, entry + buffer)
        if trailing_active:
            candidate = max(candidate, current_price - trail)
        if aggressive_trailing_active:
            candidate = max(candidate, current_price - aggressive_trail)
        # Never place SL above (price - min stop) or beyond TP.
        candidate = min(candidate, current_price - min_stop_distance, take_profit)
        if current_sl > 0 and candidate <= current_sl + tolerance:
            return None
        if candidate <= entry - reward:  # sanity: must be an improvement vs original risk
            return None
        return candidate

    # SELL: SL sits above price and is tightened downward.
    candidate = current_sl if current_sl > 0 else float("inf")
    if breakeven_active:
        candidate = min(candidate, entry - buffer)
    if trailing_active:
        candidate = min(candidate, current_price + trail)
    if aggressive_trailing_active:
        candidate = min(candidate, current_price + aggressive_trail)
    candidate = max(candidate, current_price + min_stop_distance, take_profit)
    if current_sl > 0 and candidate >= current_sl - tolerance:
        return None
    return candidate


class TradeManagementService:
    """Apply break-even and trailing-stop adjustments to open positions."""

    def __init__(
        self,
        order_executor: MT5OrderExecutor,
        settings: Any,
    ) -> None:
        self.order_executor = order_executor
        self.settings = settings

    def _config(self) -> TradeManagementConfig:
        s = self.settings
        return TradeManagementConfig(
            enabled=bool(s.trade_management_enabled),
            breakeven_trigger_ratio=float(s.trade_management_breakeven_trigger_ratio),
            breakeven_buffer_ratio=float(s.trade_management_breakeven_buffer_ratio),
            trailing_enabled=bool(s.trade_management_trailing_enabled),
            trailing_activation_ratio=float(s.trade_management_trailing_activation_ratio),
            trailing_distance_ratio=float(s.trade_management_trailing_distance_ratio),
            trailing_aggressive_activation_ratio=float(s.trade_management_trailing_aggressive_activation_ratio),
            trailing_aggressive_distance_ratio=float(s.trade_management_trailing_aggressive_distance_ratio),
            min_step_ratio=float(s.trade_management_min_step_ratio),
        )

    def manage_positions(self, positions: Iterable[Any]) -> dict[str, int]:
        config = self._config()
        if not config.enabled:
            return {"evaluated": 0, "modified": 0}

        evaluated = 0
        modified = 0
        for position in positions:
            evaluated += 1
            if self._manage_one(position, config):
                modified += 1
        return {"evaluated": evaluated, "modified": modified}

    def _manage_one(self, position: Any, config: TradeManagementConfig) -> bool:
        details = position if isinstance(position, dict) else (getattr(position, "details", None) or {})
        symbol = str(details.get("symbol", "") or "")
        ticket = int(details.get("ticket", 0) or 0)
        entry = float(details.get("price_open", 0.0) or 0.0)
        take_profit = float(details.get("tp", 0.0) or 0.0)
        current_sl = float(details.get("sl", 0.0) or 0.0)
        current_price = float(details.get("price_current", 0.0) or 0.0)
        side = "BUY" if int(details.get("type", 0) or 0) == 0 else "SELL"

        if not symbol or ticket <= 0 or entry <= 0 or take_profit <= 0 or current_price <= 0:
            return False

        try:
            min_stop = self.order_executor.get_symbol_min_stop_distance(symbol)
        except Exception:
            min_stop = 0.0

        new_sl = compute_managed_sl(
            side=side,
            entry=entry,
            take_profit=take_profit,
            current_price=current_price,
            current_sl=current_sl,
            config=config,
            min_stop_distance=min_stop,
        )
        if new_sl is None:
            return False

        result = self.order_executor.modify_position_sltp(
            ticket=ticket,
            symbol=symbol,
            sl=new_sl,
            tp=take_profit,
        )

        if result.status in (OrderExecutionStatus.FILLED, OrderExecutionStatus.DRY_RUN):
            logger.info(
                "Trade-mgmt moved SL ticket={} {} {} from {} to {:.5f} (price={}, tp={})",
                ticket,
                symbol,
                side,
                current_sl,
                new_sl,
                current_price,
                take_profit,
            )
            return result.status == OrderExecutionStatus.FILLED

        logger.warning(
            "Trade-mgmt SL modify failed ticket={} {}: {}",
            ticket,
            symbol,
            result.error_message,
        )
        return False
