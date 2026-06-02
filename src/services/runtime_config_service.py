"""Service for runtime config hot reload with DB fallback."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from src.config.runtime_config import RUNTIME_CONFIG_SPECS, coerce_runtime_config_value, get_runtime_default_values
from src.config.settings import AppSettings
from src.repositories.runtime_config_repository import RuntimeConfigRepository


class RuntimeConfigService:
    """DB-backed runtime-config loader with TTL cache and env fallback."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        bootstrap_settings: AppSettings,
        cache_ttl_seconds: float = 2.0,
    ) -> None:
        self.session_factory = session_factory
        self.bootstrap_settings = bootstrap_settings
        self.cache_ttl_seconds = max(0.0, float(cache_ttl_seconds))
        self._cache_lock = threading.Lock()
        self._cached_values: dict[str, Any] | None = None
        self._cached_details: dict[str, dict[str, Any]] | None = None
        self._loaded_at_monotonic: float = 0.0

    def invalidate_cache(self) -> None:
        with self._cache_lock:
            self._cached_values = None
            self._cached_details = None
            self._loaded_at_monotonic = 0.0

    def seed_defaults_if_missing(self, updated_by: str = "system-bootstrap") -> None:
        defaults = get_runtime_default_values(self.bootstrap_settings)
        session = self.session_factory()
        try:
            repo = RuntimeConfigRepository(session)
            for config_key, payload in defaults.items():
                repo.create_if_missing(
                    config_key=config_key,
                    config_value=payload["config_value"],
                    value_type=payload["value_type"],
                    description=payload["description"],
                    updated_by=updated_by,
                    update_reason="seed default runtime config",
                    is_active=True,
                )
            session.commit()
        finally:
            session.close()
        self.invalidate_cache()

    def _is_cache_fresh(self) -> bool:
        if self._cached_values is None:
            return False
        return (time.monotonic() - self._loaded_at_monotonic) <= self.cache_ttl_seconds

    def _load_effective_configs(self) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        defaults = get_runtime_default_values(self.bootstrap_settings)
        values = {key: payload["config_value"] for key, payload in defaults.items()}
        details: dict[str, dict[str, Any]] = {
            key: {
                "config_key": key,
                "config_value": payload["config_value"],
                "value_type": payload["value_type"],
                "description": payload["description"],
                "source": "env_fallback",
                "is_active": False,
                "updated_by": None,
                "update_reason": None,
                "validation_error": None,
            }
            for key, payload in defaults.items()
        }

        session = self.session_factory()
        try:
            repo = RuntimeConfigRepository(session)
            for row in repo.list_configs(active_only=False):
                if row.config_key not in RUNTIME_CONFIG_SPECS:
                    continue

                validation_error: str | None = None
                effective_value = values[row.config_key]
                source = "db_inactive" if not row.is_active else "db"
                if row.is_active:
                    try:
                        effective_value = coerce_runtime_config_value(row.config_key, row.config_value)
                        values[row.config_key] = effective_value
                    except (TypeError, ValueError) as exc:
                        validation_error = str(exc)
                        source = "env_fallback_invalid_db"
                        logger.warning("Invalid runtime config override ignored: key={} error={}", row.config_key, exc)

                details[row.config_key] = {
                    "config_key": row.config_key,
                    "config_value": effective_value,
                    "value_type": row.value_type,
                    "description": row.description or details[row.config_key]["description"],
                    "source": source,
                    "is_active": bool(row.is_active),
                    "updated_by": row.updated_by,
                    "update_reason": row.update_reason,
                    "validation_error": validation_error,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
        finally:
            session.close()

        return values, details

    def _ensure_cache_loaded(self, force_refresh: bool = False) -> None:
        with self._cache_lock:
            if not force_refresh and self._is_cache_fresh():
                return
            values, details = self._load_effective_configs()
            self._cached_values = values
            self._cached_details = details
            self._loaded_at_monotonic = time.monotonic()

    def get_value(self, config_key: str) -> Any:
        if config_key not in RUNTIME_CONFIG_SPECS:
            raise KeyError(f"Unknown runtime config key: {config_key}")
        self._ensure_cache_loaded()
        assert self._cached_values is not None
        return self._cached_values[config_key]

    def list_effective_configs(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        self._ensure_cache_loaded(force_refresh=force_refresh)
        assert self._cached_details is not None
        return [self._cached_details[key] for key in sorted(self._cached_details.keys())]

    def update_config(self, config_key: str, config_value: Any, updated_by: str, update_reason: str) -> dict[str, Any]:
        coerced_value = coerce_runtime_config_value(config_key, config_value)
        spec = RUNTIME_CONFIG_SPECS[config_key]

        session = self.session_factory()
        try:
            repo = RuntimeConfigRepository(session)
            row = repo.upsert_config(
                config_key=config_key,
                config_value=coerced_value,
                value_type=spec.value_type,
                description=spec.description,
                updated_by=updated_by,
                update_reason=update_reason,
                is_active=True,
            )
            session.commit()
            result = {
                "config_key": row.config_key,
                "config_value": coerced_value,
                "value_type": row.value_type,
                "description": row.description,
                "source": "db",
                "is_active": row.is_active,
                "updated_by": row.updated_by,
                "update_reason": row.update_reason,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "validation_error": None,
            }
        finally:
            session.close()

        self.invalidate_cache()
        return result
