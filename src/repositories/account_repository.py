"""Repository for trading account tables."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.infrastructure.database.models import AccountSnapshot, TradingAccount


class AccountRepository:
    """CRUD/query repository for account-related models."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_trading_account(
        self,
        account_number: str,
        account_name: str,
        broker_server: str,
        base_currency: str,
        leverage: int,
        metadata: dict[str, Any] | None = None,
    ) -> TradingAccount:
        stmt = select(TradingAccount).where(TradingAccount.account_number == account_number).limit(1)
        account = self.session.execute(stmt).scalar_one_or_none()
        if account is not None:
            return account

        account = TradingAccount(
            account_number=account_number,
            account_name=account_name,
            broker_server=broker_server,
            base_currency=base_currency,
            leverage=leverage,
            metadata_json=metadata or {},
        )
        self.session.add(account)
        self.session.flush()
        return account

    def create_account_snapshot(
        self,
        account_id: uuid.UUID,
        balance: float,
        equity: float,
        margin: float,
        free_margin: float,
        margin_level: float,
        profit: float,
        snapshot_time: datetime,
        raw_payload: dict[str, Any] | None = None,
    ) -> AccountSnapshot:
        snapshot = AccountSnapshot(
            account_id=account_id,
            balance=balance,
            equity=equity,
            margin=margin,
            free_margin=free_margin,
            margin_level=margin_level,
            profit=profit,
            snapshot_time=snapshot_time,
            raw_payload=raw_payload or {},
        )
        self.session.add(snapshot)
        self.session.flush()
        return snapshot

    def get_latest_account_snapshot(self, account_id: uuid.UUID) -> AccountSnapshot | None:
        stmt = (
            select(AccountSnapshot)
            .where(AccountSnapshot.account_id == account_id)
            .order_by(AccountSnapshot.snapshot_time.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()
