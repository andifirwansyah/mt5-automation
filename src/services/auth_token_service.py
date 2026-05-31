"""Signed access token service for dashboard API auth."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Any


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("utf-8")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_access_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_access_token(
    *,
    secret_key: str,
    user_id: str,
    email: str,
    expires_in_seconds: int,
) -> str:
    if not secret_key:
        raise ValueError("Secret key is required")
    if expires_in_seconds <= 0:
        raise ValueError("Token TTL must be greater than zero")

    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in_seconds)).timestamp()),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(secret_key.encode("utf-8"), payload_bytes, hashlib.sha256).digest()
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature)}"


def verify_access_token(*, token: str, secret_key: str) -> dict[str, Any] | None:
    if not token or not secret_key:
        return None

    parts = token.split(".")
    if len(parts) != 2:
        return None

    payload_part, signature_part = parts
    try:
        payload_bytes = _b64url_decode(payload_part)
        signature = _b64url_decode(signature_part)
    except Exception:
        return None

    expected_signature = hmac.new(secret_key.encode("utf-8"), payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_signature):
        return None

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return None

    exp = payload.get("exp")
    if not isinstance(exp, int):
        return None
    if exp < int(datetime.now(timezone.utc).timestamp()):
        return None

    return payload
