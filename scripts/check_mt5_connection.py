"""Manual MT5 connectivity and market data check (read-only)."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config.settings import get_settings
from src.infrastructure.mt5 import MT5AccountClient, MT5Connection, MT5MarketData, MT5PositionClient


def main() -> None:
    settings = get_settings()

    connection = MT5Connection(
        path=settings.mt5_path,
        login=settings.mt5_login,
        password=settings.mt5_password,
        server=settings.mt5_server,
        timeout_ms=settings.mt5_timeout_ms,
    )

    print("[INFO] Connecting to MT5...")
    connected = connection.connect()
    print(f"[INFO] MT5 connected: {connected}")
    if not connected:
        print(f"[ERROR] MT5 last error: {connection.get_last_error()}")
        return

    try:
        account_client = MT5AccountClient()
        market_data = MT5MarketData()
        position_client = MT5PositionClient()

        # 1) Account info
        account_info = account_client.get_account_info() or {}
        print("\n=== ACCOUNT INFO ===")
        print(f"login   : {account_info.get('login')}")
        print(f"server  : {account_info.get('server')}")
        print(f"balance : {account_info.get('balance')}")
        print(f"equity  : {account_info.get('equity')}")

        # 2) Candle XAUUSD M5
        symbol = "XAUUSD"
        tf = "M5"
        print(f"\n=== CANDLE CHECK ({symbol} {tf}) ===")
        selected = market_data.select_symbol(symbol)
        print(f"symbol selected: {selected}")
        rates = market_data.get_rates(symbol=symbol, timeframe=tf, count=50)
        df = market_data.normalize_rates_to_dataframe(rates)
        print(f"candles fetched: {len(df)}")
        if len(df) > 0:
            last_row = df.iloc[-1].to_dict()
            print(f"latest candle: {last_row}")

        # 3) Tick and spread
        print(f"\n=== TICK CHECK ({symbol}) ===")
        tick = market_data.get_tick(symbol)
        if tick:
            bid = tick.get("bid")
            ask = tick.get("ask")
            spread = (float(ask) - float(bid)) if ask is not None and bid is not None else None
            print(f"tick: {tick}")
            print(f"spread: {spread}")
        else:
            print("tick: None")

        # 4) Open positions
        print("\n=== OPEN POSITIONS ===")
        positions = position_client.get_open_positions()
        print(f"open positions count: {len(positions)}")
        if positions:
            print(f"sample position: {positions[0]}")

        print("\n[INFO] Read-only checks completed. No order was sent.")

    finally:
        print("\n[INFO] Shutting down MT5 connection...")
        connection.shutdown()


if __name__ == "__main__":
    main()
