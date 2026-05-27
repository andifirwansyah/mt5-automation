"""Common API response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class MessageResponse(BaseModel):
    message: str


class PaginatedResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int
