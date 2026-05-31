"""Authentication request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UserLoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class UserLoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in_seconds: int
