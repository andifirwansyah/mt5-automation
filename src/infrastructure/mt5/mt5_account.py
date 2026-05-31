"""MT5 account info adapter."""

from __future__ import annotations

from typing import Any

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover
    mt5 = None  # type: ignore[assignment]


class MT5AccountClient:
    """Adapter for account-level information from MetaTrader5."""

    @staticmethod
    def _require_mt5() -> None:
        if mt5 is None:
            raise RuntimeError("MetaTrader5 package is not available in this environment.")

    def get_account_info(self) -> dict[str, Any] | None:
        self._require_mt5()
        info = mt5.account_info()
        return info._asdict() if info is not None else None

    def to_domain_account_data(self) -> dict[str, Any] | None:
        info = self.get_account_info()
        if info is None:
            return None

        return {
            "account_number": str(info.get("login", "")),
            "account_name": str(info.get("name", "")),
            "broker_server": str(info.get("server", "")),
            "base_currency": str(info.get("currency", "")),
            "leverage": int(info.get("leverage", 0)),
            "balance": float(info.get("balance", 0.0)),
            "equity": float(info.get("equity", 0.0)),
            "margin": float(info.get("margin", 0.0)),
            "free_margin": float(info.get("margin_free", 0.0)),
            "margin_level": float(info.get("margin_level", 0.0)),
            "profit": float(info.get("profit", 0.0)),
            "raw_payload": info,
        }
