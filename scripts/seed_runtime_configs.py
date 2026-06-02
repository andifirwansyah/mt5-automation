"""Seed DB-backed runtime configuration defaults."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config.runtime_config import RUNTIME_CONFIG_SPECS, coerce_runtime_config_value
from src.infrastructure.database.session import SessionLocal
from src.repositories.runtime_config_repository import RuntimeConfigRepository


RUNTIME_CONFIG_SEEDS: list[dict[str, Any]] = [
    {
        "config_key": "max_spread",
        "config_value": 50.0,
        "value_type": "float",
        "description": "Maximum spread for signal/data validation.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "max_open_positions_per_symbol",
        "config_value": 3,
        "value_type": "int",
        "description": "Maximum open positions allowed per symbol.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "min_edge_sample_size",
        "config_value": 30,
        "value_type": "int",
        "description": "Minimum sample size for edge validation.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "allow_low_sample_edge",
        "config_value": True,
        "value_type": "bool",
        "description": "Allow low-sample edge warning mode.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "edge_min_win_rate",
        "config_value": 0.45,
        "value_type": "float",
        "description": "Minimum win rate threshold for historical edge.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "edge_min_profit_factor",
        "config_value": 1.1,
        "value_type": "float",
        "description": "Minimum profit factor threshold for historical edge.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "risk_per_trade_percent",
        "config_value": 0.5,
        "value_type": "float",
        "description": "Risk percentage per trade.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "fixed_lot",
        "config_value": 0.01,
        "value_type": "float",
        "description": "Fallback fixed lot size.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "max_lot",
        "config_value": 0.05,
        "value_type": "float",
        "description": "Maximum lot size cap.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "min_rr",
        "config_value": 1.5,
        "value_type": "float",
        "description": "Minimum risk-reward ratio.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "max_spread_points",
        "config_value": 50.0,
        "value_type": "float",
        "description": "Maximum spread points for broker health checks.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "min_margin_level",
        "config_value": 300.0,
        "value_type": "float",
        "description": "Minimum margin level requirement.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "min_free_margin",
        "config_value": 0.0,
        "value_type": "float",
        "description": "Minimum free margin requirement.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "pretrade_spread_stress_multiplier",
        "config_value": 1.5,
        "value_type": "float",
        "description": "Spread stress multiplier used in pre-trade simulation.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "pretrade_slippage_points",
        "config_value": 30.0,
        "value_type": "float",
        "description": "Synthetic slippage points for simulation.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "max_daily_loss",
        "config_value": 500.0,
        "value_type": "float",
        "description": "Maximum daily loss before safety trigger.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "max_consecutive_losses",
        "config_value": 3,
        "value_type": "int",
        "description": "Maximum consecutive losses before safety trigger.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "max_open_positions",
        "config_value": 1,
        "value_type": "int",
        "description": "Maximum total open positions before safety trigger.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "auto_apply_strategy_feedback",
        "config_value": False,
        "value_type": "bool",
        "description": "Apply strategy feedback recommendations automatically.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "feedback_min_trades",
        "config_value": 20,
        "value_type": "int",
        "description": "Minimum trades before strategy feedback activates.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "feedback_low_win_rate",
        "config_value": 0.4,
        "value_type": "float",
        "description": "Low win-rate threshold for feedback.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "feedback_high_drawdown",
        "config_value": 500.0,
        "value_type": "float",
        "description": "High drawdown threshold for feedback.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "seed default runtime config",
    },
    {
        "config_key": "max_trades_per_day",
        "config_value": 3,
        "value_type": "int",
        "description": "Maximum trades per day before safety trigger.",
        "is_active": True,
        "updated_by": "pytest",
        "update_reason": "restore after api test",
    },
]


def validate_runtime_config_seeds() -> None:
    for seed in RUNTIME_CONFIG_SEEDS:
        config_key = str(seed["config_key"])
        if config_key not in RUNTIME_CONFIG_SPECS:
            raise KeyError(f"Unknown runtime config key in seed: {config_key}")

        spec = RUNTIME_CONFIG_SPECS[config_key]
        if spec.value_type != seed["value_type"]:
            raise ValueError(
                f"Seed value_type mismatch for {config_key}: expected {spec.value_type}, got {seed['value_type']}"
            )

        seed["config_value"] = coerce_runtime_config_value(config_key, seed["config_value"])


def main() -> None:
    validate_runtime_config_seeds()

    session = SessionLocal()
    try:
        repository = RuntimeConfigRepository(session)
        for seed in RUNTIME_CONFIG_SEEDS:
            repository.upsert_config(
                config_key=seed["config_key"],
                config_value=seed["config_value"],
                value_type=seed["value_type"],
                description=seed["description"],
                updated_by=seed["updated_by"],
                update_reason=seed["update_reason"],
                is_active=bool(seed["is_active"]),
            )

        session.commit()
        print("[OK] Runtime configs seeded")
        print(f"runtime_configs: {len(RUNTIME_CONFIG_SEEDS)}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
