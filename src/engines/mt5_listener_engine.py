"""MT5 listener engine for new candle and optional tick callbacks."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from loguru import logger

from src.infrastructure.mt5.mt5_market_data import MT5MarketData
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext


class MT5ListenerEngine(PipelineStep):
    """Listen MT5 feed and emit new candle events without duplication."""

    @property
    def name(self) -> str:
        return "MT5ListenerEngine"

    def __init__(
        self,
        market_data: MT5MarketData,
        symbol: str,
        timeframe: str,
        interval_seconds: float = 1.0,
        on_new_candle: Callable[[dict[str, Any]], None] | None = None,
        on_tick: Callable[[dict[str, Any]], None] | None = None,
        tick_symbol: str | None = None,
    ) -> None:
        self.market_data = market_data
        self.symbol = symbol
        self.timeframe = timeframe
        self.interval_seconds = interval_seconds
        self.on_new_candle = on_new_candle
        self.on_tick = on_tick
        self.tick_symbol = tick_symbol or symbol

        self._last_candle_time: datetime | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _poll_once(self) -> None:
        rates = self.market_data.get_rates(self.symbol, self.timeframe, count=2)
        df = self.market_data.normalize_rates_to_dataframe(rates)
        if df.empty:
            return

        latest = df.iloc[-1].to_dict()
        latest_time = latest.get("time")
        if latest_time is None:
            return

        if self._last_candle_time is None or latest_time > self._last_candle_time:
            self._last_candle_time = latest_time
            candle_event = {
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "candle_time": latest_time.isoformat() if hasattr(latest_time, "isoformat") else str(latest_time),
                "open": float(latest.get("open", 0.0)),
                "high": float(latest.get("high", 0.0)),
                "low": float(latest.get("low", 0.0)),
                "close": float(latest.get("close", 0.0)),
                "tick_volume": int(latest.get("tick_volume", 0)),
                "spread": int(latest.get("spread", 0)) if latest.get("spread") is not None else None,
                "source": "mt5_listener",
            }
            if self.on_new_candle is not None:
                self.on_new_candle(candle_event)

        if self.on_tick is not None:
            tick = self.market_data.get_tick(self.tick_symbol)
            if tick:
                self.on_tick(tick)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception:
                logger.exception("MT5 listener poll failed")
            self._stop_event.wait(self.interval_seconds)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="mt5-listener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def run(self, context: TradingContext) -> TradingContext:
        """Listener engine is event-driven and does not mutate pipeline context directly."""

        return context
