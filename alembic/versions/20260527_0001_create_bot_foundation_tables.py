"""create bot foundation tables

Revision ID: 20260527_0001
Revises:
Create Date: 2026-05-27 14:10:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260527_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS trading")

    op.create_table(
        "bot_instances",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instance_name", sa.String(length=100), nullable=False),
        sa.Column("host_name", sa.String(length=255), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="trading",
    )
    op.create_index("ix_bot_instances_instance_name", "bot_instances", ["instance_name"], unique=False, schema="trading")

    op.create_table(
        "bot_runtime_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bot_instance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_running", sa.Boolean(), nullable=False),
        sa.Column("is_rejected", sa.Boolean(), nullable=False),
        sa.Column("rejection_reason", sa.String(length=100), nullable=True),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("context_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["bot_instance_id"], ["trading.bot_instances.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="trading",
    )
    op.create_index("ix_bot_runtime_states_bot_instance_id", "bot_runtime_states", ["bot_instance_id"], unique=False, schema="trading")
    op.create_index("ix_bot_runtime_states_trace_id", "bot_runtime_states", ["trace_id"], unique=False, schema="trading")

    op.create_table(
        "engine_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bot_instance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("engine_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_reference", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_reference", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["bot_instance_id"], ["trading.bot_instances.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema="trading",
    )
    op.create_index("ix_engine_runs_bot_instance_id", "engine_runs", ["bot_instance_id"], unique=False, schema="trading")
    op.create_index("ix_engine_runs_trace_id", "engine_runs", ["trace_id"], unique=False, schema="trading")
    op.create_index("ix_engine_runs_engine_name", "engine_runs", ["engine_name"], unique=False, schema="trading")
    op.create_index("ix_engine_runs_status", "engine_runs", ["status"], unique=False, schema="trading")
    op.create_index(
        "ix_engine_runs_trace_id_created_at",
        "engine_runs",
        ["trace_id", "created_at"],
        unique=False,
        schema="trading",
    )
    op.create_index(
        "ix_engine_runs_engine_name_created_at",
        "engine_runs",
        ["engine_name", "created_at"],
        unique=False,
        schema="trading",
    )


def downgrade() -> None:
    op.drop_index("ix_engine_runs_engine_name_created_at", table_name="engine_runs", schema="trading")
    op.drop_index("ix_engine_runs_trace_id_created_at", table_name="engine_runs", schema="trading")
    op.drop_index("ix_engine_runs_status", table_name="engine_runs", schema="trading")
    op.drop_index("ix_engine_runs_engine_name", table_name="engine_runs", schema="trading")
    op.drop_index("ix_engine_runs_trace_id", table_name="engine_runs", schema="trading")
    op.drop_index("ix_engine_runs_bot_instance_id", table_name="engine_runs", schema="trading")
    op.drop_table("engine_runs", schema="trading")

    op.drop_index("ix_bot_runtime_states_trace_id", table_name="bot_runtime_states", schema="trading")
    op.drop_index("ix_bot_runtime_states_bot_instance_id", table_name="bot_runtime_states", schema="trading")
    op.drop_table("bot_runtime_states", schema="trading")

    op.drop_index("ix_bot_instances_instance_name", table_name="bot_instances", schema="trading")
    op.drop_table("bot_instances", schema="trading")

    op.execute("DROP SCHEMA IF EXISTS trading")
