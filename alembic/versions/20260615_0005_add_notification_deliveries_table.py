"""add notification deliveries table

Revision ID: 20260615_0005
Revises: 20260615_0004
Create Date: 2026-06-15 13:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260615_0005"
down_revision = "20260615_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("recipient_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=True),
        sa.Column("provider_name", sa.String(length=32), nullable=False),
        sa.Column("session_name", sa.String(length=120), nullable=False),
        sa.Column("destination", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("narrative_provider", sa.String(length=64), nullable=False),
        sa.Column("used_fallback", sa.Boolean(), nullable=False),
        sa.Column("message_text", sa.String(length=4000), nullable=False),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["recipient_id"], ["trading.notification_recipients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="trading",
    )
    op.create_index(
        "ix_notification_deliveries_recipient_created_at",
        "notification_deliveries",
        ["recipient_id", "created_at"],
        unique=False,
        schema="trading",
    )
    op.create_index(
        "ix_notification_deliveries_event_type_created_at",
        "notification_deliveries",
        ["event_type", "created_at"],
        unique=False,
        schema="trading",
    )
    op.create_index(
        "ix_notification_deliveries_status_created_at",
        "notification_deliveries",
        ["status", "created_at"],
        unique=False,
        schema="trading",
    )


def downgrade() -> None:
    op.drop_index("ix_notification_deliveries_status_created_at", table_name="notification_deliveries", schema="trading")
    op.drop_index("ix_notification_deliveries_event_type_created_at", table_name="notification_deliveries", schema="trading")
    op.drop_index("ix_notification_deliveries_recipient_created_at", table_name="notification_deliveries", schema="trading")
    op.drop_table("notification_deliveries", schema="trading")
