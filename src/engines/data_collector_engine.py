"""Engine to collect market/account/position data from MT5 adapters."""

from __future__ import annotations

from typing import Any

from src.domain.models.market_snapshot import MarketSnapshot
from src.infrastructure.mt5.mt5_account import MT5AccountClient
from src.infrastructure.mt5.mt5_market_data import MT5MarketData
from src.infrastructure.mt5.mt5_positions import MT5PositionClient
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext


class DataCollectorEngine(PipelineStep):
    """Collects OHLCV, ticks, account info, and open positions."""

    @property
    def name(self) -> str:
        return "DataCollectorEngine"

    def __init__(
        self,
        market_data: MT5MarketData,
        account_client: MT5AccountClient,
        position_client: MT5PositionClient,
        context_timeframes: list[str] | None = None,
        entry_candle_count: int = 300,
        context_candle_count: int = 300,
    ) -> None:
        self.market_data = market_data
        self.account_client = account_client
        self.position_client = position_client
        self.context_timeframes = context_timeframes or []
        self.entry_candle_count = entry_candle_count
        self.context_candle_count = context_candle_count

    def run(self, context: TradingContext) -> TradingContext:
        symbol = context.symbol
        entry_tf = context.timeframe

        self.market_data.select_symbol(symbol)

        timeframe_list = [entry_tf] + [tf for tf in self.context_timeframes if tf != entry_tf]
        rates_by_timeframe: dict[str, Any] = {}

        for tf in timeframe_list:
            count = self.entry_candle_count if tf == entry_tf else self.context_candle_count
            rates = self.market_data.get_rates(symbol=symbol, timeframe=tf, count=count)
            rates_by_timeframe[tf] = self.market_data.normalize_rates_to_dataframe(rates)

        entry_df = rates_by_timeframe.get(entry_tf)
        tick = self.market_data.get_tick(symbol)
        account_info = self.account_client.get_account_info()
        open_positions = self.position_client.get_open_positions(symbol=None)

        if entry_df is not None and not entry_df.empty:
            last = entry_df.iloc[-1].to_dict()
            spread = last.get("spread")
            if spread is None and tick and tick.get("bid") is not None and tick.get("ask") is not None:
                spread = float(tick["ask"]) - float(tick["bid"])

            context.market_snapshot = MarketSnapshot(
                symbol=symbol,
                timeframe=entry_tf,
                candle_time=last["time"],
                open_price=float(last.get("open", 0.0)),
                high_price=float(last.get("high", 0.0)),
                low_price=float(last.get("low", 0.0)),
                close_price=float(last.get("close", 0.0)),
                tick_volume=int(last.get("tick_volume", 0)),
                spread=int(spread) if isinstance(spread, (int, float)) else None,
                bid=float(tick.get("bid")) if tick and tick.get("bid") is not None else None,
                ask=float(tick.get("ask")) if tick and tick.get("ask") is not None else None,
                features={
                    "account_equity": float(account_info.get("equity", 0.0)) if account_info else 0.0,
                    "account_balance": float(account_info.get("balance", 0.0)) if account_info else 0.0,
                },
                raw_payload={"entry_candle": last, "tick": tick},
            )

        context.ingestion_result = {
            "source": "data_collector_engine",
            "rates_by_timeframe": rates_by_timeframe,
            "tick": tick,
            "account_info": account_info,
            "open_positions": open_positions,
        }
        return context
