"""Repository for runtime configuration records."""

from __future__ import annotations

from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.infrastructure.database.models import RuntimeConfig


class RuntimeConfigRepository:
    """CRUD/query repository for DB-backed runtime configs."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_configs(self, active_only: bool = False) -> list[RuntimeConfig]:
        stmt = select(RuntimeConfig).order_by(RuntimeConfig.config_key.asc())
        if active_only:
            stmt = stmt.where(RuntimeConfig.is_active.is_(True))
        return list(self.session.execute(stmt).scalars().all())

    def get_by_key(self, config_key: str) -> RuntimeConfig | None:
        stmt = select(RuntimeConfig).where(RuntimeConfig.config_key == config_key).limit(1)
        return self.session.execute(stmt).scalar_one_or_none()

    def upsert_config(
        self,
        config_key: str,
        config_value: Any,
        value_type: str,
        description: str | None = None,
        updated_by: str | None = None,
        update_reason: str | None = None,
        is_active: bool = True,
    ) -> RuntimeConfig:
        entity = self.get_by_key(config_key)
        if entity is None:
            entity = RuntimeConfig(
                config_key=config_key,
                config_value=config_value,
                value_type=value_type,
                description=description,
                is_active=is_active,
                updated_by=updated_by,
                update_reason=update_reason,
            )
        else:
            entity.config_value = config_value
            entity.value_type = value_type
            entity.description = description or entity.description
            entity.is_active = is_active
            entity.updated_by = updated_by
            entity.update_reason = update_reason

        self.session.add(entity)
        self.session.flush()
        return entity

    def create_if_missing(
        self,
        config_key: str,
        config_value: Any,
        value_type: str,
        description: str | None = None,
        updated_by: str | None = None,
        update_reason: str | None = None,
        is_active: bool = True,
    ) -> None:
        stmt = insert(RuntimeConfig).values(
            config_key=config_key,
            config_value=config_value,
            value_type=value_type,
            description=description,
            is_active=is_active,
            updated_by=updated_by,
            update_reason=update_reason,
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=[RuntimeConfig.config_key])
        self.session.execute(stmt)
