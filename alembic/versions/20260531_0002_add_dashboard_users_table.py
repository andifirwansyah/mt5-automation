"""add dashboard users table

Revision ID: 20260531_0002
Revises: 745830deb06e
Create Date: 2026-05-31 10:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260531_0002"
down_revision = "745830deb06e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dashboard_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("password_salt", sa.String(length=255), nullable=False),
        sa.Column("hash_algorithm", sa.String(length=64), nullable=False),
        sa.Column("hash_iterations", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        schema="trading",
    )
    op.create_index("ix_dashboard_users_email", "dashboard_users", ["email"], unique=False, schema="trading")
    op.create_index("ix_dashboard_users_is_active", "dashboard_users", ["is_active"], unique=False, schema="trading")


def downgrade() -> None:
    op.drop_index("ix_dashboard_users_is_active", table_name="dashboard_users", schema="trading")
    op.drop_index("ix_dashboard_users_email", table_name="dashboard_users", schema="trading")
    op.drop_table("dashboard_users", schema="trading")
