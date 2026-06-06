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

    dashboard_auth_secret: str = Field(default="", alias="DASHBOARD_AUTH_SECRET")
    auth_token_ttl_seconds: int = Field(default=3600, alias="AUTH_TOKEN_TTL_SECONDS")

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
    account_mode: str = Field(default="DEMO_AUTO", alias="ACCOUNT_MODE")
    trading_magic_number: int = Field(default=20260527, alias="TRADING_MAGIC_NUMBER")
    order_deviation: int = Field(default=20, alias="ORDER_DEVIATION")
    max_spread: float = Field(default=50.0, alias="MAX_SPREAD")
    max_open_positions_per_symbol: int = Field(default=3, alias="MAX_OPEN_POSITIONS_PER_SYMBOL")
    min_edge_sample_size: int = Field(default=30, alias="MIN_EDGE_SAMPLE_SIZE")
    allow_low_sample_edge: bool = Field(default=True, alias="ALLOW_LOW_SAMPLE_EDGE")
    edge_min_win_rate: float = Field(default=0.45, alias="EDGE_MIN_WIN_RATE")
    edge_min_profit_factor: float = Field(default=1.1, alias="EDGE_MIN_PROFIT_FACTOR")
    risk_per_trade_percent: float = Field(default=1.0, alias="RISK_PER_TRADE_PERCENT")
    fixed_lot: float = Field(default=0.01, alias="FIXED_LOT")
    max_lot: float = Field(default=1.0, alias="MAX_LOT")
    min_rr: float = Field(default=1.2, alias="MIN_RR")
    max_spread_points: float = Field(default=50.0, alias="MAX_SPREAD_POINTS")
    min_margin_level: float = Field(default=100.0, alias="MIN_MARGIN_LEVEL")
    min_free_margin: float = Field(default=0.0, alias="MIN_FREE_MARGIN")
    pretrade_spread_stress_multiplier: float = Field(default=1.5, alias="PRETRADE_SPREAD_STRESS_MULTIPLIER")
    pretrade_slippage_points: float = Field(default=5.0, alias="PRETRADE_SLIPPAGE_POINTS")
    max_daily_loss: float = Field(default=500.0, alias="MAX_DAILY_LOSS")
    max_trades_per_day: int = Field(default=20, alias="MAX_TRADES_PER_DAY")
    max_consecutive_losses: int = Field(default=5, alias="MAX_CONSECUTIVE_LOSSES")
    max_open_positions: int = Field(default=10, alias="MAX_OPEN_POSITIONS")
    auto_apply_strategy_feedback: bool = Field(default=False, alias="AUTO_APPLY_STRATEGY_FEEDBACK")
    feedback_min_trades: int = Field(default=20, alias="FEEDBACK_MIN_TRADES")
    feedback_low_win_rate: float = Field(default=0.4, alias="FEEDBACK_LOW_WIN_RATE")
    feedback_high_drawdown: float = Field(default=500.0, alias="FEEDBACK_HIGH_DRAWDOWN")
    market_structure_override_min_confidence: float = Field(default=0.70, alias="MARKET_STRUCTURE_OVERRIDE_MIN_CONFIDENCE")
    market_structure_hard_min_room_atr: float = Field(default=0.30, alias="MARKET_STRUCTURE_HARD_MIN_ROOM_ATR")
    market_structure_soft_min_room_atr: float = Field(default=0.80, alias="MARKET_STRUCTURE_SOFT_MIN_ROOM_ATR")
    market_structure_zone_tolerance_atr: float = Field(default=0.45, alias="MARKET_STRUCTURE_ZONE_TOLERANCE_ATR")
    market_structure_danger_zone_atr: float = Field(default=0.55, alias="MARKET_STRUCTURE_DANGER_ZONE_ATR")
    market_structure_min_candles_required: int = Field(default=30, alias="MARKET_STRUCTURE_MIN_CANDLES_REQUIRED")
    session_filter_allowed_sessions: str = Field(default="ASIA,LONDON,NEW_YORK", alias="SESSION_FILTER_ALLOWED_SESSIONS")
    session_filter_block_rollover: bool = Field(default=True, alias="SESSION_FILTER_BLOCK_ROLLOVER")
    signal_quality_min_score: float = Field(default=0.45, alias="SIGNAL_QUALITY_MIN_SCORE")
    trade_cooldown_minutes: int = Field(default=10, alias="TRADE_COOLDOWN_MINUTES")
    trading_symbol: str = Field(default="XAUUSD", alias="TRADING_SYMBOL")
    trading_timeframe: str = Field(default="M5", alias="TRADING_TIMEFRAME")
    context_timeframes_csv: str = Field(default="M15,M30,H1,H4", alias="CONTEXT_TIMEFRAMES")
    listener_interval_seconds: float = Field(default=1.0, alias="LISTENER_INTERVAL_SECONDS")
    position_sync_interval_seconds: float = Field(default=5.0, alias="POSITION_SYNC_INTERVAL_SECONDS")
    account_snapshot_interval_seconds: float = Field(default=5.0, alias="ACCOUNT_SNAPSHOT_INTERVAL_SECONDS")
    heartbeat_interval_seconds: float = Field(default=10.0, alias="HEARTBEAT_INTERVAL_SECONDS")
    performance_interval_seconds: float = Field(default=300.0, alias="PERFORMANCE_INTERVAL_SECONDS")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_rotation: str = Field(default="10 MB", alias="LOG_ROTATION")
    log_retention: str = Field(default="14 days", alias="LOG_RETENTION")
    log_compression: str = Field(default="zip", alias="LOG_COMPRESSION")

    timezone: str = Field(default="UTC", alias="TIMEZONE")

    @property
    def context_timeframes(self) -> list[str]:
        """Parsed context timeframes from comma-separated env value."""

        raw_items = [item.strip().upper() for item in self.context_timeframes_csv.split(",")]
        return [item for item in raw_items if item]


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Get singleton settings instance."""

    return AppSettings()
