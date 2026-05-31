"""Broker health check engine."""

from __future__ import annotations

import uuid

from src.config.settings import AppSettings, get_settings
from src.domain.models.broker_health import BrokerHealth
from src.infrastructure.mt5.mt5_health import MT5HealthClient
from src.pipeline.pipeline_step import PipelineStep
from src.pipeline.trading_context import TradingContext
from src.repositories.execution_repository import ExecutionRepository


class BrokerHealthCheck(PipelineStep):
    """Validate broker/terminal readiness prior to execution gate."""

    @property
    def name(self) -> str:
        return "BrokerHealthCheck"

    def __init__(self, health_client: MT5HealthClient, execution_repository: ExecutionRepository, settings: AppSettings | None = None) -> None:
        self.health_client = health_client
        self.execution_repository = execution_repository
        self.settings = settings or get_settings()

    @staticmethod
    def _as_uuid(value: object) -> uuid.UUID | None:
        if isinstance(value, uuid.UUID):
            return value
        if isinstance(value, str) and value:
            try:
                return uuid.UUID(value)
            except ValueError:
                return None
        return None

    def run(self, context: TradingContext) -> TradingContext:
        is_connected = self.health_client.check_connection()
        terminal_trade_allowed = self.health_client.check_trade_allowed()
        account_info = self.health_client.account_client.get_account_info() or {}
        account_trade_allowed = bool(account_info.get("trade_allowed", True))
        symbol_trade_allowed = self.health_client.check_symbol_trade_allowed(context.symbol)

        spread = self.health_client.check_spread(context.symbol)
        spread_ok = spread is not None and float(spread) <= float(self.settings.max_spread_points)

        margin_level = self.health_client.check_margin_level()
        margin_ok = margin_level is not None and float(margin_level) >= float(self.settings.min_margin_level)

        free_margin = float(account_info.get("margin_free", 0.0))
        free_margin_ok = free_margin >= float(self.settings.min_free_margin)

        is_healthy = all(
            [
                is_connected,
                terminal_trade_allowed,
                account_trade_allowed,
                symbol_trade_allowed,
                spread_ok,
                margin_ok,
                free_margin_ok,
            ]
        )

        details = {
            "terminal_trade_allowed": terminal_trade_allowed,
            "account_trade_allowed": account_trade_allowed,
            "symbol_trade_allowed": symbol_trade_allowed,
            "spread_ok": spread_ok,
            "margin_ok": margin_ok,
            "free_margin_ok": free_margin_ok,
            "margin_level": margin_level,
            "free_margin": free_margin,
        }

        symbol_id = self._as_uuid((context.ingestion_result or {}).get("symbol_id"))

        self.execution_repository.create_broker_health_check(
            symbol_id=symbol_id,
            is_connected=is_connected,
            is_trade_allowed=terminal_trade_allowed and account_trade_allowed and symbol_trade_allowed,
            is_healthy=is_healthy,
            spread=float(spread) if spread is not None else None,
            latency_ms=None,
            details=details,
            raw_payload={"account_info": account_info},
            checked_at=context.candle_time,
        )
        self.execution_repository.session.commit()

        context.broker_health = BrokerHealth(
            is_healthy=is_healthy,
            is_connected=is_connected,
            is_trade_allowed=terminal_trade_allowed and account_trade_allowed and symbol_trade_allowed,
            spread=float(spread) if spread is not None else None,
            latency_ms=None,
            reason=None if is_healthy else "BROKER_HEALTH_FAILED",
            details=details,
        )

        if not is_healthy:
            context.reject("BROKER_HEALTH_FAILED", details)
        return context
