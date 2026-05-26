from datetime import UTC, datetime

from ai_trading_automation.modules.paper_execution.models import PaperOrder
from ai_trading_automation.modules.position_monitor import (
    MarketCandle,
    PositionMonitorRequest,
    PositionMonitorService,
)


def _open_buy_order() -> PaperOrder:
    now = datetime.now(tz=UTC)
    return PaperOrder(
        order_id="ord-1",
        signal_id="sig-1",
        symbol="XAUUSD",
        timeframe="H1",
        direction="BUY",
        entry_price=2350.0,
        stop_loss=2345.0,
        take_profit=2360.0,
        lot_size=10.0,
        status="OPEN",
        created_at=now,
        updated_at=now,
    )


def _open_sell_order() -> PaperOrder:
    now = datetime.now(tz=UTC)
    return PaperOrder(
        order_id="ord-2",
        signal_id="sig-2",
        symbol="XAUUSD",
        timeframe="H1",
        direction="SELL",
        entry_price=2350.0,
        stop_loss=2355.0,
        take_profit=2340.0,
        lot_size=10.0,
        status="OPEN",
        created_at=now,
        updated_at=now,
    )


def test_buy_take_profit_hit_detected() -> None:
    service = PositionMonitorService()
    candle = MarketCandle(
        timestamp=datetime.now(tz=UTC),
        open=2350.0,
        high=2361.0,
        low=2349.0,
        close=2358.0,
    )

    state = service.update(PositionMonitorRequest(order=_open_buy_order(), candle=candle))

    assert state.status == "CLOSED"
    assert state.exit_reason == "TAKE_PROFIT_HIT"
    assert state.hit_take_profit is True


def test_buy_stop_loss_hit_detected() -> None:
    service = PositionMonitorService()
    candle = MarketCandle(
        timestamp=datetime.now(tz=UTC),
        open=2350.0,
        high=2352.0,
        low=2344.0,
        close=2346.0,
    )

    state = service.update(PositionMonitorRequest(order=_open_buy_order(), candle=candle))

    assert state.status == "CLOSED"
    assert state.exit_reason == "STOP_LOSS_HIT"
    assert state.hit_stop_loss is True


def test_sell_take_profit_hit_detected() -> None:
    service = PositionMonitorService()
    candle = MarketCandle(
        timestamp=datetime.now(tz=UTC),
        open=2350.0,
        high=2351.0,
        low=2339.0,
        close=2341.0,
    )

    state = service.update(PositionMonitorRequest(order=_open_sell_order(), candle=candle))

    assert state.status == "CLOSED"
    assert state.exit_reason == "TAKE_PROFIT_HIT"


def test_open_position_stays_open_if_no_hit() -> None:
    service = PositionMonitorService()
    candle = MarketCandle(
        timestamp=datetime.now(tz=UTC),
        open=2350.0,
        high=2353.0,
        low=2347.0,
        close=2351.0,
    )

    state = service.update(PositionMonitorRequest(order=_open_buy_order(), candle=candle))

    assert state.status == "OPEN"
    assert state.exit_reason is None
    assert state.realized_pnl is None
