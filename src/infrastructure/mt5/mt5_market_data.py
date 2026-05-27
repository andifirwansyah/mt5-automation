"""MT5 market data adapter."""

from __future__ import annotations

from typing import Any

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None  # type: ignore[assignment]

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover
    mt5 = None  # type: ignore[assignment]


class MT5MarketData:
    """Adapter for symbol/rates/tick access from MetaTrader5."""

    TIMEFRAME_MAP: dict[str, int] = {
        "M1": getattr(mt5, "TIMEFRAME_M1", 1),
        "M5": getattr(mt5, "TIMEFRAME_M5", 5),
        "M15": getattr(mt5, "TIMEFRAME_M15", 15),
        "M30": getattr(mt5, "TIMEFRAME_M30", 30),
        "H1": getattr(mt5, "TIMEFRAME_H1", 16385),
        "H4": getattr(mt5, "TIMEFRAME_H4", 16388),
        "D1": getattr(mt5, "TIMEFRAME_D1", 16408),
    }

    @staticmethod
    def _require_mt5() -> None:
        if mt5 is None:
            raise RuntimeError("MetaTrader5 package is not available in this environment.")

    def select_symbol(self, symbol: str) -> bool:
        self._require_mt5()
        return bool(mt5.symbol_select(symbol, True))

    def get_rates(self, symbol: str, timeframe: str, count: int) -> Any:
        self._require_mt5()
        tf = self.TIMEFRAME_MAP.get(timeframe)
        if tf is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        return mt5.copy_rates_from_pos(symbol, tf, 0, count)

    def get_tick(self, symbol: str) -> dict[str, Any] | None:
        self._require_mt5()
        tick = mt5.symbol_info_tick(symbol)
        return tick._asdict() if tick is not None else None

    def get_symbol_info(self, symbol: str) -> dict[str, Any] | None:
        self._require_mt5()
        info = mt5.symbol_info(symbol)
        return info._asdict() if info is not None else None

    def normalize_rates_to_dataframe(self, rates: Any) -> Any:
        if pd is None:
            raise RuntimeError("pandas is not available in this environment.")
        if rates is None:
            return pd.DataFrame()
        df = pd.DataFrame(rates)
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        return df
