"""Authentication endpoints for dashboard access."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.api.deps_auth import require_authenticated_user
from src.config.settings import get_settings
from src.repositories.auth_repository import AuthRepository
from src.schemas import MessageResponse, UserLoginRequest, UserLoginResponse
from src.services.auth_token_service import generate_access_token
from src.services.password_hasher_service import verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=UserLoginResponse)
def login_user(payload: UserLoginRequest, db: Session = Depends(get_db)) -> UserLoginResponse:
    settings = get_settings()
    if not settings.dashboard_auth_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth secret is not configured")

    auth_repo = AuthRepository(db)
    user = auth_repo.get_user_by_email(payload.email)

    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    password_valid = verify_password(
        payload.password,
        password_hash=user.password_hash,
        password_salt=user.password_salt,
        hash_algorithm=user.hash_algorithm,
        hash_iterations=user.hash_iterations,
    )

    if not password_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    auth_repo.update_last_login(user_id=user.id, login_at=datetime.now(timezone.utc))
    db.commit()

    access_token = generate_access_token(
        secret_key=settings.dashboard_auth_secret,
        user_id=str(user.id),
        email=user.email,
        expires_in_seconds=settings.auth_token_ttl_seconds,
    )

    return UserLoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in_seconds=settings.auth_token_ttl_seconds,
    )


@router.post("/logout", response_model=MessageResponse)
def logout_user(
    current_user: dict = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    auth_repo = AuthRepository(db)

    user_id_raw = current_user.get("user_id")
    token_hash_raw = current_user.get("token_hash")
    exp_raw = current_user.get("exp")
    if not isinstance(user_id_raw, str) or not isinstance(token_hash_raw, str) or not isinstance(exp_raw, int):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication context")

    auth_repo.revoke_token(
        user_id=uuid.UUID(user_id_raw),
        token_hash=token_hash_raw,
        expires_at=datetime.fromtimestamp(exp_raw, tz=timezone.utc),
        reason="LOGOUT",
        metadata={"email": current_user.get("email")},
    )
    db.commit()
    return MessageResponse(message="Logged out")
