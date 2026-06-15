"""add notification recipient tables

Revision ID: 20260615_0004
Revises: 0d2148a0f3ff
Create Date: 2026-06-15 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260615_0004"
down_revision = "0d2148a0f3ff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_recipients",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("channel_type", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("destination", sa.String(length=255), nullable=False),
        sa.Column("session_name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "channel_type",
            "destination",
            "session_name",
            name="uq_notification_recipients_channel_destination_session",
        ),
        schema="trading",
    )
    op.create_index(
        "ix_notification_recipients_channel_active",
        "notification_recipients",
        ["channel_type", "is_active"],
        unique=False,
        schema="trading",
    )
    op.create_index(
        "ix_notification_recipients_destination",
        "notification_recipients",
        ["destination"],
        unique=False,
        schema="trading",
    )

    op.create_table(
        "notification_subscriptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("recipient_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["recipient_id"], ["trading.notification_recipients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recipient_id", "event_type", name="uq_notification_subscriptions_recipient_event_type"),
        schema="trading",
    )
    op.create_index(
        "ix_notification_subscriptions_recipient_active",
        "notification_subscriptions",
        ["recipient_id", "is_active"],
        unique=False,
        schema="trading",
    )
    op.create_index(
        "ix_notification_subscriptions_event_type",
        "notification_subscriptions",
        ["event_type"],
        unique=False,
        schema="trading",
    )


def downgrade() -> None:
    op.drop_index("ix_notification_subscriptions_event_type", table_name="notification_subscriptions", schema="trading")
    op.drop_index("ix_notification_subscriptions_recipient_active", table_name="notification_subscriptions", schema="trading")
    op.drop_table("notification_subscriptions", schema="trading")
    op.drop_index("ix_notification_recipients_destination", table_name="notification_recipients", schema="trading")
    op.drop_index("ix_notification_recipients_channel_active", table_name="notification_recipients", schema="trading")
    op.drop_table("notification_recipients", schema="trading")
