"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Runtime settings for bot worker and API server."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="AI Trading Automation", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")

    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/ai_trading",
        alias="DATABASE_URL",
    )

    mt5_login: int = Field(default=0, alias="MT5_LOGIN")
    mt5_password: str = Field(default="", alias="MT5_PASSWORD")
    mt5_server: str = Field(default="", alias="MT5_SERVER")
    mt5_path: str = Field(default="", alias="MT5_PATH")
    mt5_timeout_ms: int = Field(default=10000, alias="MT5_TIMEOUT_MS")

    auto_trade: bool = Field(default=True, alias="AUTO_TRADE")
    approval_required: bool = Field(default=False, alias="APPROVAL_REQUIRED")
    dry_run: bool = Field(default=True, alias="DRY_RUN")
    trading_magic_number: int = Field(default=20260527, alias="TRADING_MAGIC_NUMBER")
    order_deviation: int = Field(default=20, alias="ORDER_DEVIATION")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_rotation: str = Field(default="10 MB", alias="LOG_ROTATION")
    log_retention: str = Field(default="14 days", alias="LOG_RETENTION")
    log_compression: str = Field(default="zip", alias="LOG_COMPRESSION")

    timezone: str = Field(default="UTC", alias="TIMEZONE")


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Get singleton settings instance."""

    return AppSettings()
