"""Engine to persist collected market/account data into PostgreSQL."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories.account_repository import AccountRepository
from src.repositories.market_repository import MarketRepository
from src.services.account_snapshot_service import AccountSnapshotService
from src.services.candle_service import CandleService


class MarketDataIngestionEngine(PipelineStep):
    """Stores candles, ticks, and account snapshots in database."""

    @property
    def name(self) -> str:
        return "MarketDataIngestionEngine"

    def __init__(
        self,
        market_repository: MarketRepository,
        account_repository: AccountRepository,
        candle_service: CandleService,
        account_snapshot_service: AccountSnapshotService,
    ) -> None:
        self.market_repository = market_repository
        self.account_repository = account_repository
        self.candle_service = candle_service
        self.account_snapshot_service = account_snapshot_service

    @staticmethod
    def _timeframe_to_minutes(timeframe: str) -> int:
        if timeframe.startswith("M"):
            return int(timeframe[1:])
        if timeframe.startswith("H"):
            return int(timeframe[1:]) * 60
        if timeframe == "D1":
            return 1440
        return 1

    @staticmethod
    def _parse_tick_time(tick: dict[str, Any] | None) -> datetime:
        if not tick:
            return datetime.now(timezone.utc)
        ts = tick.get("time")
        if ts is None:
            return datetime.now(timezone.utc)
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {k: MarketDataIngestionEngine._json_safe(v) for k, v in value.items()}
        if isinstance(value, list):
            return [MarketDataIngestionEngine._json_safe(v) for v in value]
        return value

    def run(self, context: TradingContext) -> TradingContext:
        collected = context.ingestion_result or {}
        rates_by_timeframe = collected.get("rates_by_timeframe", {})
        tick = collected.get("tick")
        account_info = collected.get("account_info")

        symbol = self.market_repository.get_or_create_symbol(name=context.symbol)

        timeframe_ids: dict[str, Any] = {}
        candles_saved = 0
        duplicate_entry_candle = False

        candle_payloads: list[dict[str, Any]] = []
        for tf, df in rates_by_timeframe.items():
            timeframe = self.market_repository.get_or_create_timeframe(
                code=tf,
                minutes=self._timeframe_to_minutes(tf),
                description=tf,
            )
            timeframe_ids[tf] = timeframe.id

            if df is None or df.empty:
                continue

            if tf == context.timeframe:
                entry_last = df.iloc[-1]
                duplicate_entry_candle = self.candle_service.detect_duplicate(
                    symbol_id=symbol.id,
                    timeframe_id=timeframe.id,
                    open_time=entry_last["time"],
                )

            for _, row in df.iterrows():
                candle_payloads.append(
                    {
                        "symbol_id": symbol.id,
                        "timeframe_id": timeframe.id,
                        "open_time": row["time"],
                        "open_price": float(row.get("open", 0.0)),
                        "high_price": float(row.get("high", 0.0)),
                        "low_price": float(row.get("low", 0.0)),
                        "close_price": float(row.get("close", 0.0)),
                        "tick_volume": int(row.get("tick_volume", 0)),
                        "spread": int(row.get("spread", 0)) if row.get("spread") is not None else None,
                        "real_volume": int(row.get("real_volume", 0)) if row.get("real_volume") is not None else None,
                        "features": {},
                        "raw_payload": self._json_safe(row.to_dict()),
                    }
                )

        if candle_payloads:
            candles_saved = len(self.candle_service.save_candles(candle_payloads))

        tick_saved = False
        if tick:
            self.market_repository.create_tick_snapshot(
                symbol_id=symbol.id,
                event_time=self._parse_tick_time(tick),
                bid=float(tick.get("bid", 0.0)),
                ask=float(tick.get("ask", 0.0)),
                last=float(tick.get("last", 0.0)) if tick.get("last") is not None else None,
                spread=(float(tick.get("ask", 0.0)) - float(tick.get("bid", 0.0))) if tick.get("ask") is not None and tick.get("bid") is not None else None,
                raw_payload=self._json_safe(tick),
            )
            tick_saved = True

        account_snapshot_saved = False
        if account_info:
            account = self.account_repository.get_or_create_trading_account(
                account_number=str(account_info.get("login", "")),
                account_name=str(account_info.get("name", "")),
                broker_server=str(account_info.get("server", "")),
                base_currency=str(account_info.get("currency", "")),
                leverage=int(account_info.get("leverage", 0)),
                metadata={"source": "mt5"},
            )
            self.account_snapshot_service.save_account_snapshot(account_id=account.id, payload=account_info)
            account_snapshot_saved = True

        self.market_repository.session.commit()

        context.ingestion_result = {
            **collected,
            "source": "market_data_ingestion_engine",
            "symbol_id": symbol.id,
            "timeframe_ids": timeframe_ids,
            "candles_saved": candles_saved,
            "tick_saved": tick_saved,
            "account_snapshot_saved": account_snapshot_saved,
            "duplicate_entry_candle": duplicate_entry_candle,
        }
        return context
