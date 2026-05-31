"""Upsert dashboard login user into database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.infrastructure.database.session import SessionLocal
from src.repositories.auth_repository import AuthRepository
from src.services.password_hasher_service import hash_password


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed or update dashboard user credential")
    parser.add_argument("--email", required=True, help="Dashboard user email")
    parser.add_argument("--password", required=True, help="Dashboard user password")
    parser.add_argument("--inactive", action="store_true", help="Create/update user as inactive")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    session = SessionLocal()
    try:
        password_result = hash_password(args.password)
        repo = AuthRepository(session)
        user = repo.upsert_dashboard_user(
            email=args.email,
            password_hash=password_result.password_hash,
            password_salt=password_result.password_salt,
            hash_algorithm=password_result.hash_algorithm,
            hash_iterations=password_result.hash_iterations,
            is_active=not args.inactive,
            metadata={"seeded_by": "seed_dashboard_user.py"},
        )
        session.commit()
        print(f"[OK] dashboard user upserted: {user.email} (active={user.is_active})")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
