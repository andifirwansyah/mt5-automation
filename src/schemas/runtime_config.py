"""Schemas for runtime config API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RuntimeConfigUpdatePayload(BaseModel):
    value: Any
    actor: str = Field(default="api")
    reason: str = Field(default="manual_update")
