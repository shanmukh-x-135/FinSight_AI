"""add versioned strategies and deterministic backtest results

Revision ID: 0017_strategy_backtesting
Revises: 0016_news_evidence
Create Date: 2026-08-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_strategy_backtesting"
down_revision: str | None = "0016_news_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        )
    ]


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(1000)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_strategies_user_updated", "strategies", ["user_id", "updated_at"])
    op.create_table(
        "strategy_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "strategy_id",
            sa.Integer(),
            sa.ForeignKey("strategies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("strategy_id", "version", name="uq_strategy_version"),
    )
    op.create_index(
        "ix_strategy_versions_strategy_id", "strategy_versions", ["strategy_id"]
    )
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "strategy_version_id",
            sa.Integer(),
            sa.ForeignKey("strategy_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("universe_code", sa.String(32), nullable=False),
        sa.Column("membership_mode", sa.String(32), nullable=False),
        sa.Column("membership_disclaimer", sa.String(500), nullable=False),
        sa.Column("benchmark_symbol", sa.String(32), nullable=False),
        sa.Column("definition_snapshot", sa.JSON(), nullable=False),
        sa.Column("equity_curve", sa.JSON(), nullable=False),
        sa.Column("result_hash", sa.String(64)),
        sa.Column("error_summary", sa.Text()),
        *_timestamps(),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_backtest_runs_user_created", "backtest_runs", ["user_id", "created_at"]
    )
    op.create_index("ix_backtest_runs_result_hash", "backtest_runs", ["result_hash"])
    op.create_table(
        "backtest_trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("backtest_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "stock_id",
            sa.Integer(),
            sa.ForeignKey("stocks.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("entry_signal_date", sa.Date(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("exit_signal_date", sa.Date()),
        sa.Column("exit_date", sa.Date(), nullable=False),
        sa.Column("exit_price", sa.Float(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("gross_pnl", sa.Float(), nullable=False),
        sa.Column("net_pnl", sa.Float(), nullable=False),
        sa.Column("return_percent", sa.Float(), nullable=False),
        sa.Column("holding_sessions", sa.Integer(), nullable=False),
        sa.Column("exit_reason", sa.String(40), nullable=False),
        sa.Column("transaction_cost", sa.Float(), nullable=False),
    )
    op.create_index(
        "ix_backtest_trades_run_entry", "backtest_trades", ["run_id", "entry_date"]
    )
    op.create_table(
        "backtest_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("backtest_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("value", sa.Float()),
        sa.UniqueConstraint("run_id", "name", name="uq_backtest_metric_run_name"),
    )
    op.create_index("ix_backtest_metrics_run_id", "backtest_metrics", ["run_id"])


def downgrade() -> None:
    op.drop_table("backtest_metrics")
    op.drop_table("backtest_trades")
    op.drop_table("backtest_runs")
    op.drop_table("strategy_versions")
    op.drop_table("strategies")
