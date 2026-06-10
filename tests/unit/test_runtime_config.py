from __future__ import annotations

from src.config.runtime_config import RuntimeSettingsProxy
from src.config.runtime_config import RUNTIME_CONFIG_SPECS, coerce_runtime_config_value
from src.config.settings import get_settings
from src.infrastructure.database.session import SessionLocal
from src.repositories.runtime_config_repository import RuntimeConfigRepository
from src.services.runtime_config_service import RuntimeConfigService


def test_runtime_settings_proxy_reads_db_update_without_recreating_proxy() -> None:
    settings = get_settings()
    service = RuntimeConfigService(SessionLocal, settings, cache_ttl_seconds=0.0)
    service.seed_defaults_if_missing(updated_by="pytest")
    runtime_settings = RuntimeSettingsProxy(settings, service)

    original_value = int(runtime_settings.max_trades_per_day)
    updated_value = original_value + 1

    session = SessionLocal()
    try:
        RuntimeConfigRepository(session).upsert_config(
            config_key="max_trades_per_day",
            config_value=updated_value,
            value_type="int",
            description="pytest update",
            updated_by="pytest",
            update_reason="hot reload test",
            is_active=True,
        )
        session.commit()
    finally:
        session.close()

    assert runtime_settings.max_trades_per_day == updated_value

    restore_session = SessionLocal()
    try:
        RuntimeConfigRepository(restore_session).upsert_config(
            config_key="max_trades_per_day",
            config_value=original_value,
            value_type="int",
            description="restore",
            updated_by="pytest",
            update_reason="restore",
            is_active=True,
        )
        restore_session.commit()
    finally:
        restore_session.close()


def test_market_structure_runtime_config_specs_are_registered() -> None:
    assert "market_structure_override_min_confidence" in RUNTIME_CONFIG_SPECS
    assert "market_structure_hard_min_room_atr" in RUNTIME_CONFIG_SPECS
    assert "market_structure_soft_min_room_atr" in RUNTIME_CONFIG_SPECS
    assert "market_structure_zone_tolerance_atr" in RUNTIME_CONFIG_SPECS
    assert "market_structure_danger_zone_atr" in RUNTIME_CONFIG_SPECS
    assert "market_structure_min_candles_required" in RUNTIME_CONFIG_SPECS
    assert "position_sync_interval_seconds" in RUNTIME_CONFIG_SPECS
    assert "trade_management_trailing_aggressive_activation_ratio" in RUNTIME_CONFIG_SPECS
    assert "trade_management_trailing_aggressive_distance_ratio" in RUNTIME_CONFIG_SPECS
    assert coerce_runtime_config_value("market_structure_override_min_confidence", "0.72") == 0.72
    assert coerce_runtime_config_value("market_structure_min_candles_required", "50") == 50
    assert coerce_runtime_config_value("position_sync_interval_seconds", "1.5") == 1.5
    assert coerce_runtime_config_value("trade_management_trailing_aggressive_distance_ratio", "0.1") == 0.1
