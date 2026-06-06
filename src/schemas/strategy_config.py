"""Schemas for strategy configuration API requests."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class StrategyConfigUpdatePayload(BaseModel):
    """Payload for updating an existing strategy config row."""

    config: dict[str, Any] | None = Field(default=None)
    is_active: bool | None = Field(default=None)
    actor: str = Field(default="api", min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_has_update_field(self) -> "StrategyConfigUpdatePayload":
        if self.config is None and self.is_active is None:
            raise ValueError("At least one of config or is_active must be provided")
        return self
