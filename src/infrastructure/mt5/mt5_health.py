"""MT5 health check adapter."""

from __future__ import annotations

from src.domain.models.broker_health import BrokerHealth
from src.infrastructure.mt5.mt5_account import MT5AccountClient
from src.infrastructure.mt5.mt5_connection import MT5Connection
from src.infrastructure.mt5.mt5_market_data import MT5MarketData


BrokerHealthResult = BrokerHealth


class MT5HealthClient:
    """Adapter for broker and terminal health checks."""

    def __init__(self, connection: MT5Connection, market_data: MT5MarketData, account_client: MT5AccountClient) -> None:
        self.connection = connection
        self.market_data = market_data
        self.account_client = account_client

    def check_connection(self) -> bool:
        return self.connection.is_connected()

    def check_trade_allowed(self) -> bool:
        info = self.connection.get_terminal_info() or {}
        return bool(info.get("trade_allowed", False))

    def check_symbol_trade_allowed(self, symbol: str) -> bool:
        info = self.market_data.get_symbol_info(symbol) or {}
        trade_mode = int(info.get("trade_mode", 0))
        return trade_mode != 0

    def check_spread(self, symbol: str) -> float | None:
        tick = self.market_data.get_tick(symbol)
        if not tick:
            return None
        bid = tick.get("bid")
        ask = tick.get("ask")
        if bid is None or ask is None:
            return None
        return float(ask) - float(bid)

    def check_margin_level(self) -> float | None:
        account = self.account_client.get_account_info() or {}
        margin_level = account.get("margin_level")
        return float(margin_level) if margin_level is not None else None

    def build_broker_health_result(self, symbol: str | None = None) -> BrokerHealthResult:
        is_connected = self.check_connection()
        is_trade_allowed = self.check_trade_allowed()

        spread = None
        if symbol:
            spread = self.check_spread(symbol)
            symbol_allowed = self.check_symbol_trade_allowed(symbol)
        else:
            symbol_allowed = True

        margin_level = self.check_margin_level()
        is_healthy = bool(is_connected and is_trade_allowed and symbol_allowed)

        return BrokerHealthResult(
            is_healthy=is_healthy,
            is_connected=is_connected,
            is_trade_allowed=is_trade_allowed and symbol_allowed,
            spread=spread,
            latency_ms=None,
            reason=None if is_healthy else "BROKER_HEALTH_CHECK_FAILED",
            details={"margin_level": margin_level, "symbol": symbol},
        )
