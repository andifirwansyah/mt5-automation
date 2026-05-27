"""MT5 connection adapter."""

from __future__ import annotations

from typing import Any

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover - expected in non-Windows CI
    mt5 = None  # type: ignore[assignment]


class MT5Connection:
    """Wrapper for MetaTrader5 initialize/login/shutdown lifecycle."""

    def __init__(
        self,
        path: str,
        login: int,
        password: str,
        server: str,
        timeout_ms: int = 10000,
    ) -> None:
        self.path = path
        self.login = login
        self.password = password
        self.server = server
        self.timeout_ms = timeout_ms

    @staticmethod
    def _require_mt5() -> None:
        if mt5 is None:
            raise RuntimeError("MetaTrader5 package is not available in this environment.")

    def connect(self) -> bool:
        self._require_mt5()
        initialized = mt5.initialize(path=self.path, login=self.login, password=self.password, server=self.server, timeout=self.timeout_ms)
        return bool(initialized)

    def shutdown(self) -> None:
        self._require_mt5()
        mt5.shutdown()

    def is_connected(self) -> bool:
        self._require_mt5()
        info = mt5.terminal_info()
        return info is not None

    def get_version(self) -> tuple[int, int, str] | None:
        self._require_mt5()
        return mt5.version()

    def get_terminal_info(self) -> dict[str, Any] | None:
        self._require_mt5()
        info = mt5.terminal_info()
        return info._asdict() if info is not None else None

    def get_last_error(self) -> tuple[int, str] | None:
        self._require_mt5()
        return mt5.last_error()
