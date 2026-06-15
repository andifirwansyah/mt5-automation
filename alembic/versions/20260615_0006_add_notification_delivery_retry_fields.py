"""add notification delivery retry fields

Revision ID: 20260615_0006
Revises: 20260615_0005
Create Date: 2026-06-15 14:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260615_0006"
down_revision = "20260615_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notification_deliveries", sa.Column("retry_of_delivery_id", sa.UUID(), nullable=True), schema="trading")
    op.add_column(
        "notification_deliveries",
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        schema="trading",
    )
    op.create_foreign_key(
        "fk_notification_deliveries_retry_of_delivery_id",
        "notification_deliveries",
        "notification_deliveries",
        ["retry_of_delivery_id"],
        ["id"],
        source_schema="trading",
        referent_schema="trading",
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_notification_deliveries_retry_of_delivery_id",
        "notification_deliveries",
        ["retry_of_delivery_id"],
        unique=False,
        schema="trading",
    )


def downgrade() -> None:
    op.drop_index("ix_notification_deliveries_retry_of_delivery_id", table_name="notification_deliveries", schema="trading")
    op.drop_constraint(
        "fk_notification_deliveries_retry_of_delivery_id",
        "notification_deliveries",
        schema="trading",
        type_="foreignkey",
    )
    op.drop_column("notification_deliveries", "attempt_number", schema="trading")
    op.drop_column("notification_deliveries", "retry_of_delivery_id", schema="trading")
