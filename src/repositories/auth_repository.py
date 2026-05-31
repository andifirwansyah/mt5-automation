"""Repository for dashboard user authentication."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.infrastructure.database.models import DashboardTokenRevocation, DashboardUser


class AuthRepository:
    """Data access for dashboard user credentials."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_user_by_email(self, email: str) -> DashboardUser | None:
        normalized_email = email.strip().lower()
        stmt = select(DashboardUser).where(DashboardUser.email == normalized_email).limit(1)
        return self.session.execute(stmt).scalar_one_or_none()

    def create_dashboard_user(
        self,
        email: str,
        password_hash: str,
        password_salt: str,
        hash_algorithm: str,
        hash_iterations: int,
        is_active: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> DashboardUser:
        user = DashboardUser(
            email=email.strip().lower(),
            password_hash=password_hash,
            password_salt=password_salt,
            hash_algorithm=hash_algorithm,
            hash_iterations=hash_iterations,
            is_active=is_active,
            metadata_json=metadata or {},
        )
        self.session.add(user)
        self.session.flush()
        return user

    def upsert_dashboard_user(
        self,
        email: str,
        password_hash: str,
        password_salt: str,
        hash_algorithm: str,
        hash_iterations: int,
        is_active: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> DashboardUser:
        user = self.get_user_by_email(email=email)
        if user is None:
            return self.create_dashboard_user(
                email=email,
                password_hash=password_hash,
                password_salt=password_salt,
                hash_algorithm=hash_algorithm,
                hash_iterations=hash_iterations,
                is_active=is_active,
                metadata=metadata,
            )

        user.password_hash = password_hash
        user.password_salt = password_salt
        user.hash_algorithm = hash_algorithm
        user.hash_iterations = hash_iterations
        user.is_active = is_active
        if metadata is not None:
            user.metadata_json = metadata
        self.session.add(user)
        self.session.flush()
        return user

    def update_last_login(self, user_id: uuid.UUID, login_at: datetime) -> DashboardUser | None:
        user = self.session.get(DashboardUser, user_id)
        if user is None:
            return None

        user.last_login_at = login_at
        self.session.add(user)
        self.session.flush()
        return user

    def is_token_revoked(self, token_hash: str) -> bool:
        stmt = select(DashboardTokenRevocation.id).where(DashboardTokenRevocation.token_hash == token_hash).limit(1)
        return self.session.execute(stmt).scalar_one_or_none() is not None

    def revoke_token(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DashboardTokenRevocation:
        existing = self.session.execute(
            select(DashboardTokenRevocation).where(DashboardTokenRevocation.token_hash == token_hash).limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        row = DashboardTokenRevocation(
            user_id=user_id,
            token_hash=token_hash,
            reason=reason,
            expires_at=expires_at,
            metadata_json=metadata or {},
        )
        self.session.add(row)
        self.session.flush()
        return row
