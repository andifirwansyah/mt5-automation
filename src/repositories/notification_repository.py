"""Repository for notification recipients and subscriptions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, aliased

from src.infrastructure.database.models import NotificationDelivery, NotificationRecipient, NotificationSubscription


class NotificationRepository:
    """CRUD/query abstraction for notification onboarding data."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_recipients(
        self,
        *,
        channel_type: str,
        limit: int,
        offset: int,
        include_inactive: bool = False,
    ) -> list[NotificationRecipient]:
        stmt = select(NotificationRecipient).where(NotificationRecipient.channel_type == channel_type)
        if not include_inactive:
            stmt = stmt.where(NotificationRecipient.is_active.is_(True))
        stmt = stmt.order_by(NotificationRecipient.updated_at.desc(), NotificationRecipient.created_at.desc())
        return list(self.session.execute(stmt.limit(limit).offset(offset)).scalars().all())

    def count_recipients(self, *, channel_type: str, include_inactive: bool = False) -> int:
        stmt = select(func.count()).select_from(NotificationRecipient).where(NotificationRecipient.channel_type == channel_type)
        if not include_inactive:
            stmt = stmt.where(NotificationRecipient.is_active.is_(True))
        return int(self.session.execute(stmt).scalar_one())

    def get_recipient_by_id(self, recipient_id: uuid.UUID) -> NotificationRecipient | None:
        stmt = select(NotificationRecipient).where(NotificationRecipient.id == recipient_id).limit(1)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_recipient_by_channel_destination_session(
        self,
        *,
        channel_type: str,
        destination: str,
        session_name: str,
    ) -> NotificationRecipient | None:
        stmt = (
            select(NotificationRecipient)
            .where(NotificationRecipient.channel_type == channel_type)
            .where(NotificationRecipient.destination == destination)
            .where(NotificationRecipient.session_name == session_name)
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def create_recipient(
        self,
        *,
        channel_type: str,
        display_name: str,
        destination: str,
        session_name: str,
        is_active: bool,
        metadata: dict[str, Any] | None = None,
    ) -> NotificationRecipient:
        entity = NotificationRecipient(
            channel_type=channel_type,
            display_name=display_name,
            destination=destination,
            session_name=session_name,
            is_active=is_active,
            metadata_json=metadata or {},
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def update_recipient(
        self,
        recipient: NotificationRecipient,
        *,
        display_name: str | None = None,
        destination: str | None = None,
        session_name: str | None = None,
        is_active: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> NotificationRecipient:
        if display_name is not None:
            recipient.display_name = display_name
        if destination is not None:
            recipient.destination = destination
        if session_name is not None:
            recipient.session_name = session_name
        if is_active is not None:
            recipient.is_active = is_active
        if metadata is not None:
            recipient.metadata_json = metadata
        self.session.add(recipient)
        self.session.flush()
        return recipient

    def list_subscriptions(self, recipient_id: uuid.UUID, *, active_only: bool = False) -> list[NotificationSubscription]:
        stmt = select(NotificationSubscription).where(NotificationSubscription.recipient_id == recipient_id)
        if active_only:
            stmt = stmt.where(NotificationSubscription.is_active.is_(True))
        stmt = stmt.order_by(NotificationSubscription.event_type.asc())
        return list(self.session.execute(stmt).scalars().all())

    def replace_subscriptions(
        self,
        *,
        recipient_id: uuid.UUID,
        event_types: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> list[NotificationSubscription]:
        desired = {event_type.strip() for event_type in event_types if event_type.strip()}
        existing_rows = {row.event_type: row for row in self.list_subscriptions(recipient_id)}

        for event_type, row in existing_rows.items():
            row.is_active = event_type in desired
            if metadata is not None:
                row.metadata_json = metadata
            self.session.add(row)

        for event_type in sorted(desired):
            if event_type in existing_rows:
                continue
            row = NotificationSubscription(
                recipient_id=recipient_id,
                event_type=event_type,
                is_active=True,
                metadata_json=metadata or {},
            )
            self.session.add(row)

        self.session.flush()
        return self.list_subscriptions(recipient_id, active_only=True)

    def list_recipients_by_event(
        self,
        *,
        channel_type: str,
        event_type: str,
        recipient_ids: list[uuid.UUID] | None = None,
        active_only: bool = True,
    ) -> list[NotificationRecipient]:
        stmt = (
            select(NotificationRecipient)
            .join(NotificationSubscription, NotificationSubscription.recipient_id == NotificationRecipient.id)
            .where(NotificationRecipient.channel_type == channel_type)
            .where(NotificationSubscription.event_type == event_type)
        )
        if active_only:
            stmt = stmt.where(NotificationRecipient.is_active.is_(True)).where(NotificationSubscription.is_active.is_(True))
        if recipient_ids:
            stmt = stmt.where(NotificationRecipient.id.in_(recipient_ids))
        stmt = stmt.order_by(NotificationRecipient.updated_at.desc(), NotificationRecipient.created_at.desc())
        return list(self.session.execute(stmt).scalars().unique().all())

    def create_delivery(
        self,
        *,
        recipient_id: uuid.UUID,
        event_type: str | None,
        provider_name: str,
        session_name: str,
        destination: str,
        status: str,
        provider_message_id: str | None,
        retry_of_delivery_id: uuid.UUID | None = None,
        attempt_number: int = 1,
        narrative_provider: str,
        used_fallback: bool,
        message_text: str,
        error_message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> NotificationDelivery:
        entity = NotificationDelivery(
            recipient_id=recipient_id,
            event_type=event_type,
            provider_name=provider_name,
            session_name=session_name,
            destination=destination,
            status=status,
            provider_message_id=provider_message_id,
            retry_of_delivery_id=retry_of_delivery_id,
            attempt_number=attempt_number,
            narrative_provider=narrative_provider,
            used_fallback=used_fallback,
            message_text=message_text,
            error_message=error_message,
            details=details or {},
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def list_deliveries(
        self,
        *,
        limit: int,
        offset: int,
        recipient_id: uuid.UUID | None = None,
        event_type: str | None = None,
        status: str | None = None,
    ) -> list[NotificationDelivery]:
        stmt = select(NotificationDelivery)
        if recipient_id is not None:
            stmt = stmt.where(NotificationDelivery.recipient_id == recipient_id)
        if event_type is not None:
            stmt = stmt.where(NotificationDelivery.event_type == event_type)
        if status is not None:
            stmt = stmt.where(NotificationDelivery.status == status)
        stmt = stmt.order_by(NotificationDelivery.created_at.desc()).limit(limit).offset(offset)
        return list(self.session.execute(stmt).scalars().all())

    def count_deliveries(
        self,
        *,
        recipient_id: uuid.UUID | None = None,
        event_type: str | None = None,
        status: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(NotificationDelivery)
        if recipient_id is not None:
            stmt = stmt.where(NotificationDelivery.recipient_id == recipient_id)
        if event_type is not None:
            stmt = stmt.where(NotificationDelivery.event_type == event_type)
        if status is not None:
            stmt = stmt.where(NotificationDelivery.status == status)
        return int(self.session.execute(stmt).scalar_one())

    def get_delivery_by_id(self, delivery_id: uuid.UUID) -> NotificationDelivery | None:
        stmt = select(NotificationDelivery).where(NotificationDelivery.id == delivery_id).limit(1)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_recipient_ids_with_source_delivery(
        self,
        *,
        event_type: str,
        source_key: str,
    ) -> list[uuid.UUID]:
        stmt = (
            select(NotificationDelivery.recipient_id)
            .where(NotificationDelivery.event_type == event_type)
            .where(NotificationDelivery.details["source_key"].astext == source_key)
        )
        return [row[0] for row in self.session.execute(stmt).all()]

    def list_retry_candidates(self, *, max_attempts: int, limit: int) -> list[NotificationDelivery]:
        retry_child = aliased(NotificationDelivery)
        retry_child_exists = exists(select(retry_child.id).where(retry_child.retry_of_delivery_id == NotificationDelivery.id))
        stmt = (
            select(NotificationDelivery)
            .where(NotificationDelivery.status == "failed")
            .where(NotificationDelivery.attempt_number < max_attempts)
            .where(~retry_child_exists)
            .order_by(NotificationDelivery.created_at.asc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_exhaustion_candidates(self, *, min_attempts: int, limit: int) -> list[NotificationDelivery]:
        child_alias = aliased(NotificationDelivery)
        child_exists = exists(select(child_alias.id).where(child_alias.retry_of_delivery_id == NotificationDelivery.id))
        stmt = (
            select(NotificationDelivery)
            .where(NotificationDelivery.status == "failed")
            .where(NotificationDelivery.attempt_number >= min_attempts)
            .where(~child_exists)
            .order_by(NotificationDelivery.created_at.asc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def update_delivery_status(
        self,
        delivery: NotificationDelivery,
        *,
        status: str,
        error_message: str | None = None,
        details_patch: dict[str, Any] | None = None,
    ) -> NotificationDelivery:
        delivery.status = status
        if error_message is not None:
            delivery.error_message = error_message
        if details_patch:
            merged_details = dict(delivery.details or {})
            merged_details.update(details_patch)
            delivery.details = merged_details
        self.session.add(delivery)
        self.session.flush()
        return delivery
