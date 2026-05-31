"""Service to sync MT5 open positions into database."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.infrastructure.database.models import Position
from src.infrastructure.mt5.mt5_positions import MT5PositionClient
from src.repositories.market_repository import MarketRepository
from src.repositories.position_repository import PositionRepository


class PositionSyncService:
    """Synchronize current MT5 positions with DB position records."""

    def __init__(
        self,
        position_client: MT5PositionClient,
        position_repository: PositionRepository,
        market_repository: MarketRepository,
    ) -> None:
        self.position_client = position_client
        self.position_repository = position_repository
        self.market_repository = market_repository

    def sync_open_positions(self, account_id: uuid.UUID) -> list[Position]:
        mt5_positions = self.position_client.get_open_positions()
        synced: list[Position] = []

        for row in mt5_positions:
            symbol_name = str(row.get("symbol", ""))
            symbol = self.market_repository.get_or_create_symbol(name=symbol_name)

            side = "BUY" if int(row.get("type", 0)) == 0 else "SELL"
            opened_at = datetime.fromtimestamp(int(row.get("time", 0)), tz=timezone.utc)

            synced.append(
                self.position_repository.upsert_position(
                    account_id=account_id,
                    symbol_id=symbol.id,
                    side=side,
                    volume_lot=float(row.get("volume", 0.0)),
                    entry_price=float(row.get("price_open", 0.0)),
                    stop_loss=float(row.get("sl", 0.0)),
                    take_profit=float(row.get("tp", 0.0)),
                    status="OPEN",
                    opened_at=opened_at,
                    mt5_position_ticket=int(row.get("ticket", 0)),
                    details=row,
                )
            )

        self.position_repository.session.commit()
        return synced
