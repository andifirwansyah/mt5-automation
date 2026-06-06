"""Runtime-config registry and hot-reload settings proxy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.config.settings import AppSettings


@dataclass(frozen=True)
class RuntimeConfigSpec:
    """Allowed runtime-editable config specification."""

    key: str
    value_type: str
    description: str
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] | None = None


RUNTIME_CONFIG_SPECS: dict[str, RuntimeConfigSpec] = {
    "max_spread": RuntimeConfigSpec("max_spread", "float", "Maximum spread for signal/data validation.", minimum=0),
    "max_open_positions_per_symbol": RuntimeConfigSpec(
        "max_open_positions_per_symbol",
        "int",
        "Maximum open positions allowed per symbol.",
        minimum=0,
    ),
    "min_edge_sample_size": RuntimeConfigSpec("min_edge_sample_size", "int", "Minimum sample size for edge validation.", minimum=0),
    "allow_low_sample_edge": RuntimeConfigSpec("allow_low_sample_edge", "bool", "Allow low-sample edge warning mode."),
    "edge_min_win_rate": RuntimeConfigSpec("edge_min_win_rate", "float", "Minimum win rate threshold for historical edge.", minimum=0, maximum=1),
    "edge_min_profit_factor": RuntimeConfigSpec("edge_min_profit_factor", "float", "Minimum profit factor threshold for historical edge.", minimum=0),
    "risk_per_trade_percent": RuntimeConfigSpec("risk_per_trade_percent", "float", "Risk percentage per trade.", minimum=0, maximum=1),
    "fixed_lot": RuntimeConfigSpec("fixed_lot", "float", "Fallback fixed lot size.", minimum=0),
    "max_lot": RuntimeConfigSpec("max_lot", "float", "Maximum lot size cap.", minimum=0),
    "min_rr": RuntimeConfigSpec("min_rr", "float", "Minimum risk-reward ratio.", minimum=0),
    "max_spread_points": RuntimeConfigSpec("max_spread_points", "float", "Maximum spread points for broker health checks.", minimum=0),
    "min_margin_level": RuntimeConfigSpec("min_margin_level", "float", "Minimum margin level requirement.", minimum=0),
    "min_free_margin": RuntimeConfigSpec("min_free_margin", "float", "Minimum free margin requirement.", minimum=0),
    "pretrade_spread_stress_multiplier": RuntimeConfigSpec(
        "pretrade_spread_stress_multiplier",
        "float",
        "Spread stress multiplier used in pre-trade simulation.",
        minimum=0,
    ),
    "pretrade_slippage_points": RuntimeConfigSpec("pretrade_slippage_points", "float", "Synthetic slippage points for simulation.", minimum=0),
    "max_daily_loss": RuntimeConfigSpec("max_daily_loss", "float", "Maximum daily loss before safety trigger.", minimum=0),
    "max_trades_per_day": RuntimeConfigSpec("max_trades_per_day", "int", "Maximum trades per day before safety trigger.", minimum=0),
    "max_consecutive_losses": RuntimeConfigSpec(
        "max_consecutive_losses",
        "int",
        "Maximum consecutive losses before safety trigger.",
        minimum=0,
    ),
    "max_open_positions": RuntimeConfigSpec("max_open_positions", "int", "Maximum total open positions before safety trigger.", minimum=0),
    "auto_apply_strategy_feedback": RuntimeConfigSpec(
        "auto_apply_strategy_feedback",
        "bool",
        "Apply strategy feedback recommendations automatically.",
    ),
    "feedback_min_trades": RuntimeConfigSpec("feedback_min_trades", "int", "Minimum trades before strategy feedback activates.", minimum=0),
    "feedback_low_win_rate": RuntimeConfigSpec("feedback_low_win_rate", "float", "Low win-rate threshold for feedback.", minimum=0, maximum=1),
    "feedback_high_drawdown": RuntimeConfigSpec("feedback_high_drawdown", "float", "High drawdown threshold for feedback.", minimum=0),
    "market_structure_override_min_confidence": RuntimeConfigSpec(
        "market_structure_override_min_confidence",
        "float",
        "Minimum signal confidence required to convert soft market-structure issues into warnings.",
        minimum=0,
        maximum=1,
    ),
    "market_structure_hard_min_room_atr": RuntimeConfigSpec(
        "market_structure_hard_min_room_atr",
        "float",
        "Critical minimum room-to-opposite-zone in ATR before hard reject.",
        minimum=0,
    ),
    "market_structure_soft_min_room_atr": RuntimeConfigSpec(
        "market_structure_soft_min_room_atr",
        "float",
        "Preferred minimum room-to-opposite-zone in ATR before soft warning/reject.",
        minimum=0,
    ),
    "market_structure_zone_tolerance_atr": RuntimeConfigSpec(
        "market_structure_zone_tolerance_atr",
        "float",
        "Support/resistance zone tolerance in ATR.",
        minimum=0,
    ),
    "market_structure_danger_zone_atr": RuntimeConfigSpec(
        "market_structure_danger_zone_atr",
        "float",
        "Distance to opposite support/resistance in ATR considered dangerous.",
        minimum=0,
    ),
    "market_structure_min_candles_required": RuntimeConfigSpec(
        "market_structure_min_candles_required",
        "int",
        "Minimum candles required for market-structure analysis.",
        minimum=1,
    ),
    "session_filter_allowed_sessions": RuntimeConfigSpec(
        "session_filter_allowed_sessions",
        "str",
        "Comma-separated allowed UTC sessions: ASIA,LONDON,NEW_YORK,ROLLOVER.",
    ),
    "session_filter_block_rollover": RuntimeConfigSpec(
        "session_filter_block_rollover",
        "bool",
        "Block trading during UTC rollover session.",
    ),
    "signal_quality_min_score": RuntimeConfigSpec(
        "signal_quality_min_score",
        "float",
        "Minimum composite signal quality score required before validation.",
        minimum=0,
        maximum=1,
    ),
    "trade_cooldown_minutes": RuntimeConfigSpec(
        "trade_cooldown_minutes",
        "int",
        "Cooldown minutes between generated signals for the same symbol/timeframe.",
        minimum=0,
    ),
}


def is_runtime_config_key(key: str) -> bool:
    return key in RUNTIME_CONFIG_SPECS


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"Invalid bool value: {value!r}")


def coerce_runtime_config_value(key: str, value: Any) -> Any:
    spec = RUNTIME_CONFIG_SPECS.get(key)
    if spec is None:
        raise KeyError(f"Unknown runtime config key: {key}")

    if spec.value_type == "bool":
        coerced = _coerce_bool(value)
    elif spec.value_type == "int":
        coerced = int(value)
    elif spec.value_type == "float":
        coerced = float(value)
    elif spec.value_type == "str":
        coerced = str(value).strip()
    else:  # pragma: no cover
        raise ValueError(f"Unsupported runtime config type: {spec.value_type}")

    if isinstance(coerced, (int, float)) and spec.minimum is not None and coerced < spec.minimum:
        raise ValueError(f"{key} must be >= {spec.minimum}")
    if isinstance(coerced, (int, float)) and spec.maximum is not None and coerced > spec.maximum:
        raise ValueError(f"{key} must be <= {spec.maximum}")
    if spec.choices is not None and str(coerced).upper() not in spec.choices:
        raise ValueError(f"{key} must be one of: {', '.join(spec.choices)}")
    if spec.choices is not None and isinstance(coerced, str):
        coerced = coerced.upper()
    return coerced


def get_runtime_default_values(settings: AppSettings) -> dict[str, dict[str, Any]]:
    """Build default runtime-config payloads from bootstrap settings."""

    defaults: dict[str, dict[str, Any]] = {}
    for key, spec in RUNTIME_CONFIG_SPECS.items():
        defaults[key] = {
            "config_value": coerce_runtime_config_value(key, getattr(settings, key)),
            "value_type": spec.value_type,
            "description": spec.description,
        }
    return defaults


class RuntimeSettingsProxy:
    """Settings adapter that resolves runtime-editable values from DB-backed service."""

    def __init__(self, bootstrap_settings: AppSettings, runtime_config_service: Any) -> None:
        self._bootstrap_settings = bootstrap_settings
        self._runtime_config_service = runtime_config_service

    def __getattr__(self, item: str) -> Any:
        if item in RUNTIME_CONFIG_SPECS:
            return self._runtime_config_service.get_value(item)
        return getattr(self._bootstrap_settings, item)
