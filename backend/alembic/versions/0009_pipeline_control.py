"""add durable EOD pipeline control plane

Revision ID: 0009_pipeline_control
Revises: 0008_user_admin
Create Date: 2026-08-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_pipeline_control"
down_revision: str | None = "0008_user_admin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

run_status = sa.Enum(
    "pending",
    "running",
    "partial",
    "completed",
    "failed",
    name="pipeline_run_status",
)
step_status = sa.Enum(
    "pending",
    "running",
    "completed",
    "failed",
    "skipped",
    name="pipeline_step_status",
)


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pipeline_name", sa.String(length=100), nullable=False),
        sa.Column("target_trading_date", sa.Date(), nullable=False),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("status", run_status, nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("counters", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("last_error_summary", sa.String(length=500)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "pipeline_name",
            "target_trading_date",
            name="uq_pipeline_runs_name_target_date",
        ),
    )
    op.create_index(
        "ix_pipeline_runs_correlation_id",
        "pipeline_runs",
        ["correlation_id"],
        unique=True,
    )
    op.create_index(
        "ix_pipeline_runs_status_heartbeat",
        "pipeline_runs",
        ["status", "heartbeat_at"],
    )

    op.create_table(
        "pipeline_run_steps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_name", sa.String(length=50), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", step_status, nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("counters", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("last_error_summary", sa.String(length=500)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("run_id", "step_name", name="uq_pipeline_run_steps_run_step"),
    )
    op.create_index("ix_pipeline_run_steps_run_id", "pipeline_run_steps", ["run_id"])
    op.create_index(
        "ix_pipeline_run_steps_status_heartbeat",
        "pipeline_run_steps",
        ["status", "heartbeat_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pipeline_run_steps_status_heartbeat", table_name="pipeline_run_steps"
    )
    op.drop_index("ix_pipeline_run_steps_run_id", table_name="pipeline_run_steps")
    op.drop_table("pipeline_run_steps")
    op.drop_index("ix_pipeline_runs_status_heartbeat", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_correlation_id", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
    step_status.drop(op.get_bind(), checkfirst=True)
    run_status.drop(op.get_bind(), checkfirst=True)
