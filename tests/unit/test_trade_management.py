"""Unit tests for break-even / trailing-stop SL computation."""

from __future__ import annotations

import pytest

from src.domain.enums import OrderExecutionStatus
from src.domain.models.order_result import OrderResult
from src.services.trade_management_service import TradeManagementConfig, compute_managed_sl


def _config(**overrides) -> TradeManagementConfig:
    base = dict(
        enabled=True,
        breakeven_trigger_ratio=0.60,
        breakeven_buffer_ratio=0.05,
        trailing_enabled=True,
        trailing_activation_ratio=0.60,
        trailing_distance_ratio=0.40,
        trailing_aggressive_activation_ratio=0.80,
        trailing_aggressive_distance_ratio=0.10,
        min_step_ratio=0.02,
    )
    base.update(overrides)
    return TradeManagementConfig(**base)


# --- BUY ---------------------------------------------------------------------

def test_buy_below_trigger_returns_none():
    # entry 100, tp 110 (reward 10), price 104 -> 40% progress, below 60% trigger
    result = compute_managed_sl(
        side="BUY", entry=100.0, take_profit=110.0,
        current_price=104.0, current_sl=95.0, config=_config(),
    )
    assert result is None


def test_buy_breakeven_moves_sl_to_entry_plus_buffer():
    # price 106 -> 60% progress. Trailing would give 106 - 0.4*10 = 102.0,
    # break-even gives 100 + 0.05*10 = 100.5. Max wins -> 102.0
    result = compute_managed_sl(
        side="BUY", entry=100.0, take_profit=110.0,
        current_price=106.0, current_sl=95.0, config=_config(),
    )
    assert result == pytest.approx(102.0)


def test_buy_breakeven_only_when_trailing_disabled():
    result = compute_managed_sl(
        side="BUY", entry=100.0, take_profit=110.0,
        current_price=106.0, current_sl=95.0,
        config=_config(trailing_enabled=False),
    )
    assert result == pytest.approx(100.5)


def test_buy_sl_never_moves_backward():
    # trailing candidate 102.0 is below the existing 103.0 SL -> no change
    result = compute_managed_sl(
        side="BUY", entry=100.0, take_profit=110.0,
        current_price=106.0, current_sl=103.0, config=_config(),
    )
    assert result is None


def test_buy_clamped_by_min_stop_distance():
    # price 109 (90% progress). aggressive trailing -> 109 - 1 = 108. min stop 1.0 -> max allowed 108.
    result = compute_managed_sl(
        side="BUY", entry=100.0, take_profit=110.0,
        current_price=109.0, current_sl=104.0, config=_config(),
        min_stop_distance=1.0,
    )
    assert result == pytest.approx(108.0)


def test_buy_unset_sl_is_improved():
    result = compute_managed_sl(
        side="BUY", entry=100.0, take_profit=110.0,
        current_price=106.0, current_sl=0.0, config=_config(),
    )
    assert result == pytest.approx(102.0)


# --- SELL --------------------------------------------------------------------

def test_sell_breakeven_and_trailing():
    # entry 100, tp 90 (reward 10), price 94 -> 60% progress.
    # break-even: 100 - 0.5 = 99.5 ; trailing: 94 + 4 = 98.0 ; min wins -> 98.0
    result = compute_managed_sl(
        side="SELL", entry=100.0, take_profit=90.0,
        current_price=94.0, current_sl=105.0, config=_config(),
    )
    assert result == pytest.approx(98.0)


def test_sell_sl_never_moves_backward():
    result = compute_managed_sl(
        side="SELL", entry=100.0, take_profit=90.0,
        current_price=94.0, current_sl=97.0, config=_config(),
    )
    assert result is None


def test_sell_clamped_by_min_stop_distance():
    # price 91 (90%). aggressive trailing -> 91 + 1 = 92. min stop 1 -> min allowed 92.
    result = compute_managed_sl(
        side="SELL", entry=100.0, take_profit=90.0,
        current_price=91.0, current_sl=96.0, config=_config(),
        min_stop_distance=1.0,
    )
    assert result == pytest.approx(92.0)


def test_aggressive_trailing_is_not_used_before_its_trigger():
    result = compute_managed_sl(
        side="BUY", entry=100.0, take_profit=110.0,
        current_price=107.0, current_sl=102.0, config=_config(),
    )
    assert result == pytest.approx(103.0)


class _DummyExecutor:
    def __init__(self) -> None:
        self.calls: list[dict[str, float | int | str]] = []

    @staticmethod
    def get_symbol_min_stop_distance(symbol: str) -> float:
        assert symbol == "XAUUSD"
        return 0.0

    def modify_position_sltp(self, ticket: int, symbol: str, sl: float, tp: float) -> OrderResult:
        self.calls.append({"ticket": ticket, "symbol": symbol, "sl": sl, "tp": tp})
        return OrderResult(status=OrderExecutionStatus.FILLED, dry_run=False)


class _DummySettings:
    trade_management_enabled = True
    trade_management_breakeven_trigger_ratio = 0.60
    trade_management_breakeven_buffer_ratio = 0.05
    trade_management_trailing_enabled = True
    trade_management_trailing_activation_ratio = 0.60
    trade_management_trailing_distance_ratio = 0.40
    trade_management_trailing_aggressive_activation_ratio = 0.80
    trade_management_trailing_aggressive_distance_ratio = 0.10
    trade_management_min_step_ratio = 0.02


def test_manage_positions_accepts_raw_mt5_dict_positions():
    from src.services.trade_management_service import TradeManagementService

    executor = _DummyExecutor()
    service = TradeManagementService(order_executor=executor, settings=_DummySettings())

    summary = service.manage_positions(
        [
            {
                "ticket": 123456,
                "symbol": "XAUUSD",
                "type": 0,
                "price_open": 100.0,
                "tp": 110.0,
                "sl": 95.0,
                "price_current": 109.0,
            }
        ]
    )

    assert summary == {"evaluated": 1, "modified": 1}
    assert executor.calls == [{"ticket": 123456, "symbol": "XAUUSD", "sl": 108.0, "tp": 110.0}]


# --- guards ------------------------------------------------------------------

def test_zero_reward_returns_none():
    result = compute_managed_sl(
        side="BUY", entry=100.0, take_profit=100.0,
        current_price=101.0, current_sl=95.0, config=_config(),
    )
    assert result is None


def test_adverse_price_returns_none():
    # price moved against a BUY -> negative progress
    result = compute_managed_sl(
        side="BUY", entry=100.0, take_profit=110.0,
        current_price=98.0, current_sl=95.0, config=_config(),
    )
    assert result is None
