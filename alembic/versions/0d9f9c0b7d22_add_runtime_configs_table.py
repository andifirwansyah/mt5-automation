"""add runtime configs table

Revision ID: 0d9f9c0b7d22
Revises: 745830deb06e
Create Date: 2026-06-02 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0d9f9c0b7d22"
down_revision = "745830deb06e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_configs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("config_key", sa.String(length=100), nullable=False),
        sa.Column("config_value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("value_type", sa.String(length=16), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.String(length=100), nullable=True),
        sa.Column("update_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("config_key"),
        schema="trading",
    )
    op.create_index(
        "ix_runtime_configs_config_key",
        "runtime_configs",
        ["config_key"],
        unique=True,
        schema="trading",
    )
    op.create_index(
        "ix_runtime_configs_is_active_updated_at",
        "runtime_configs",
        ["is_active", "updated_at"],
        unique=False,
        schema="trading",
    )


def downgrade() -> None:
    op.drop_index("ix_runtime_configs_is_active_updated_at", table_name="runtime_configs", schema="trading")
    op.drop_index("ix_runtime_configs_config_key", table_name="runtime_configs", schema="trading")
    op.drop_table("runtime_configs", schema="trading")
