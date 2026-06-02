"""Authentication dependencies for protected API routes."""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.config.settings import get_settings
from src.repositories.auth_repository import AuthRepository
from src.services.auth_token_service import hash_access_token, verify_access_token


bearer_scheme = HTTPBearer(auto_error=False)


def parse_bearer_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")

    scheme = str(credentials.scheme or "")
    token = str(credentials.credentials or "")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header")
    return token


def require_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> dict:
    token = parse_bearer_token(credentials)

    return authenticate_access_token(token=token, db=db)


def authenticate_access_token(token: str, db: Session) -> dict:
    """Validate token and return authenticated user context."""

    settings = get_settings()
    if not settings.dashboard_auth_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth secret is not configured")

    token_hash = hash_access_token(token)
    repo = AuthRepository(db)
    if repo.is_token_revoked(token_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")

    payload = verify_access_token(token=token, secret_key=settings.dashboard_auth_secret)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user_id_raw = payload.get("sub")
    if not isinstance(user_id_raw, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    try:
        user_id = uuid.UUID(user_id_raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject") from exc

    email_raw = payload.get("email")
    if not isinstance(email_raw, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    exp_raw = payload.get("exp")
    if not isinstance(exp_raw, int):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user = repo.get_user_by_email(email_raw)
    if user is None or not user.is_active or user.id != user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is not authorized")

    return {
        "user_id": str(user.id),
        "email": user.email,
        "exp": exp_raw,
        "token_hash": token_hash,
    }
