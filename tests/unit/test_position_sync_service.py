from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.services.position_sync_service import PositionSyncService


def test_position_sync_service_links_execution_order_and_updates_profit() -> None:
    expected_execution_order_id = uuid.uuid4()
    captured: dict[str, object] = {}

    class FakePositionClient:
        @staticmethod
        def get_open_positions() -> list[dict]:
            return [
                {
                    "ticket": 987654,
                    "symbol": "XAUUSD",
                    "type": 0,
                    "volume": 0.10,
                    "price_open": 2300.0,
                    "sl": 2295.0,
                    "tp": 2310.0,
                    "profit": 12.5,
                    "time": int(datetime.now(timezone.utc).timestamp()),
                }
            ]

    class FakeSymbol:
        id = uuid.uuid4()

    class FakeMarketRepo:
        @staticmethod
        def get_or_create_symbol(name: str):
            assert name == "XAUUSD"
            return FakeSymbol()

    class FakePosition:
        def __init__(self, details: dict) -> None:
            self.details = details

    class FakePositionRepo:
        class Session:
            @staticmethod
            def commit() -> None:
                return None

        def __init__(self) -> None:
            self.session = self.Session()

        @staticmethod
        def find_matching_execution_order_id(**kwargs):
            assert kwargs["side"] == "BUY"
            return expected_execution_order_id

        def upsert_position(self, **kwargs):
            captured.update(kwargs)
            return FakePosition(details=kwargs["details"])

    service = PositionSyncService(
        position_client=FakePositionClient(),
        position_repository=FakePositionRepo(),
        market_repository=FakeMarketRepo(),
    )

    result = service.sync_open_positions(account_id=uuid.uuid4())

    assert len(result) == 1
    assert captured["execution_order_id"] == expected_execution_order_id
    assert captured["profit"] == 12.5
    assert captured["mt5_position_ticket"] == 987654
