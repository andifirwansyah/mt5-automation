"""add dashboard token revocations table

Revision ID: 20260531_0003
Revises: 20260531_0002
Create Date: 2026-05-31 11:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260531_0003"
down_revision = "20260531_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dashboard_token_revocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["trading.dashboard_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
        schema="trading",
    )
    op.create_index(
        "ix_dashboard_token_revocations_token_hash",
        "dashboard_token_revocations",
        ["token_hash"],
        unique=False,
        schema="trading",
    )
    op.create_index(
        "ix_dashboard_token_revocations_user_id",
        "dashboard_token_revocations",
        ["user_id"],
        unique=False,
        schema="trading",
    )
    op.create_index(
        "ix_dashboard_token_revocations_expires_at",
        "dashboard_token_revocations",
        ["expires_at"],
        unique=False,
        schema="trading",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_dashboard_token_revocations_expires_at",
        table_name="dashboard_token_revocations",
        schema="trading",
    )
    op.drop_index(
        "ix_dashboard_token_revocations_user_id",
        table_name="dashboard_token_revocations",
        schema="trading",
    )
    op.drop_index(
        "ix_dashboard_token_revocations_token_hash",
        table_name="dashboard_token_revocations",
        schema="trading",
    )
    op.drop_table("dashboard_token_revocations", schema="trading")
