"""Initial MySQL schema for pipeline persistence.

Revision ID: 20260524_0001
Revises:
Create Date: 2026-05-24
"""

from alembic import op
import sqlalchemy as sa


revision = "20260524_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    execution_decision_enum = sa.Enum(
        "APPROVE",
        "REDUCE_RISK",
        "WAIT",
        "REJECT",
        name="execution_decision_type",
    )
    signal_direction_enum = sa.Enum("BUY", "SELL", "WAIT", name="signal_direction_type")
    pipeline_status_enum = sa.Enum("SUCCESS", "FAILED", name="pipeline_run_status")
    paper_order_status_enum = sa.Enum(
        "OPEN",
        "CLOSED",
        "CANCELLED",
        "REJECTED",
        name="paper_order_status",
    )

    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("status", pipeline_status_enum, nullable=False),
        sa.Column("decision", execution_decision_enum, nullable=True),
        sa.Column("failed_stage", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", name="uq_pipeline_runs_run_id"),
    )
    op.create_index("ix_pipeline_runs_status_created_at", "pipeline_runs", ["status", "created_at"])
    op.create_index(
        "ix_pipeline_runs_symbol_timeframe_created_at",
        "pipeline_runs",
        ["symbol", "timeframe", "created_at"],
    )
    op.create_index("ix_pipeline_runs_decision_created_at", "pipeline_runs", ["decision", "created_at"])

    op.create_table(
        "trade_journal_entries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("journal_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("decision", execution_decision_enum, nullable=True),
        sa.Column("signal_id", sa.String(length=36), nullable=True),
        sa.Column("symbol", sa.String(length=16), nullable=True),
        sa.Column("timeframe", sa.String(length=8), nullable=True),
        sa.Column("signal", sa.JSON(), nullable=True),
        sa.Column("signal_validation", sa.JSON(), nullable=False),
        sa.Column("risk_plan", sa.JSON(), nullable=False),
        sa.Column("simulation_result", sa.JSON(), nullable=False),
        sa.Column("execution_decision", sa.JSON(), nullable=False),
        sa.Column("order_state", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("notes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("journal_id", name="uq_trade_journal_entries_journal_id"),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.run_id"], name="fk_trade_journal_run_id"),
    )
    op.create_index(
        "ix_trade_journal_entries_decision_created_at",
        "trade_journal_entries",
        ["decision", "created_at"],
    )
    op.create_index(
        "ix_trade_journal_entries_symbol_timeframe_created_at",
        "trade_journal_entries",
        ["symbol", "timeframe", "created_at"],
    )
    op.create_index("ix_trade_journal_entries_signal_id", "trade_journal_entries", ["signal_id"])
    op.create_index("ix_trade_journal_entries_run_id", "trade_journal_entries", ["run_id"])

    op.create_table(
        "paper_orders",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("signal_id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("direction", signal_direction_enum, nullable=False),
        sa.Column("entry_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("stop_loss", sa.Numeric(18, 6), nullable=True),
        sa.Column("take_profit", sa.Numeric(18, 6), nullable=True),
        sa.Column("lot_size", sa.Numeric(18, 8), nullable=False),
        sa.Column("status", paper_order_status_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("order_id", name="uq_paper_orders_order_id"),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.run_id"], name="fk_paper_orders_run_id"),
    )
    op.create_index("ix_paper_orders_run_id", "paper_orders", ["run_id"])
    op.create_index("ix_paper_orders_signal_id", "paper_orders", ["signal_id"])
    op.create_index("ix_paper_orders_status_updated_at", "paper_orders", ["status", "updated_at"])
    op.create_index(
        "ix_paper_orders_symbol_timeframe_status",
        "paper_orders",
        ["symbol", "timeframe", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_paper_orders_symbol_timeframe_status", table_name="paper_orders")
    op.drop_index("ix_paper_orders_status_updated_at", table_name="paper_orders")
    op.drop_index("ix_paper_orders_signal_id", table_name="paper_orders")
    op.drop_index("ix_paper_orders_run_id", table_name="paper_orders")
    op.drop_table("paper_orders")

    op.drop_index("ix_trade_journal_entries_run_id", table_name="trade_journal_entries")
    op.drop_index("ix_trade_journal_entries_signal_id", table_name="trade_journal_entries")
    op.drop_index("ix_trade_journal_entries_symbol_timeframe_created_at", table_name="trade_journal_entries")
    op.drop_index("ix_trade_journal_entries_decision_created_at", table_name="trade_journal_entries")
    op.drop_table("trade_journal_entries")

    op.drop_index("ix_pipeline_runs_decision_created_at", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_symbol_timeframe_created_at", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_status_created_at", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
