"""Password hashing service for dashboard authentication."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass


DEFAULT_HASH_ALGORITHM = "PBKDF2_SHA256"
DEFAULT_HASH_ITERATIONS = 210000


@dataclass(frozen=True)
class PasswordHashResult:
    hash_algorithm: str
    hash_iterations: int
    password_hash: str
    password_salt: str


def hash_password(
    password: str,
    *,
    iterations: int = DEFAULT_HASH_ITERATIONS,
    algorithm: str = DEFAULT_HASH_ALGORITHM,
) -> PasswordHashResult:
    if not password:
        raise ValueError("Password cannot be empty")
    if iterations <= 0:
        raise ValueError("Iterations must be greater than zero")
    if algorithm != DEFAULT_HASH_ALGORITHM:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")

    salt_bytes = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, iterations)
    return PasswordHashResult(
        hash_algorithm=DEFAULT_HASH_ALGORITHM,
        hash_iterations=iterations,
        password_hash=digest.hex(),
        password_salt=salt_bytes.hex(),
    )


def verify_password(
    password: str,
    *,
    password_hash: str,
    password_salt: str,
    hash_algorithm: str,
    hash_iterations: int,
) -> bool:
    if hash_algorithm != DEFAULT_HASH_ALGORITHM:
        return False

    try:
        salt_bytes = bytes.fromhex(password_salt)
        expected_hash = bytes.fromhex(password_hash)
    except ValueError:
        return False

    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, hash_iterations)
    return hmac.compare_digest(digest, expected_hash)
