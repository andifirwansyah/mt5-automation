"""MT5 positions adapter."""

from __future__ import annotations

from typing import Any

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover
    mt5 = None  # type: ignore[assignment]


class MT5PositionClient:
    """Adapter for open positions retrieval from MetaTrader5."""

    @staticmethod
    def _require_mt5() -> None:
        if mt5 is None:
            raise RuntimeError("MetaTrader5 package is not available in this environment.")

    def get_open_positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        self._require_mt5()
        positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        if positions is None:
            return []
        return [p._asdict() for p in positions]

    def get_position_by_ticket(self, ticket: int) -> dict[str, Any] | None:
        self._require_mt5()
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return None
        return positions[0]._asdict()

    def to_domain_position_data(self, position: dict[str, Any]) -> dict[str, Any]:
        return {
            "ticket": int(position.get("ticket", 0)),
            "symbol": str(position.get("symbol", "")),
            "type": int(position.get("type", -1)),
            "volume": float(position.get("volume", 0.0)),
            "price_open": float(position.get("price_open", 0.0)),
            "sl": float(position.get("sl", 0.0)),
            "tp": float(position.get("tp", 0.0)),
            "price_current": float(position.get("price_current", 0.0)),
            "profit": float(position.get("profit", 0.0)),
            "time": int(position.get("time", 0)),
            "raw_payload": position,
        }
