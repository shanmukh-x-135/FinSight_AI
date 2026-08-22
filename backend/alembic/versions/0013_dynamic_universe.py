"""add effective-dated dynamic index universe

Revision ID: 0013_dynamic_universe
Revises: 0012_history_index_state
Create Date: 2026-08-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_dynamic_universe"
down_revision: str | None = "0012_history_index_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "stocks", sa.Column("exchange_symbol", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "stocks",
        sa.Column(
            "data_provider",
            sa.String(length=32),
            server_default="yahoo",
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_stocks_exchange_symbol"), "stocks", ["exchange_symbol"], unique=False
    )
    op.execute(
        """
        UPDATE stocks
        SET exchange_symbol = LEFT(symbol, LENGTH(symbol) - 3)
        WHERE exchange = 'NSE' AND symbol LIKE '%.NS'
        """
    )

    op.create_table(
        "universe_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("index_code", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("constituent_count", sa.Integer(), nullable=False),
        sa.Column("constituents", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "index_code",
            "source",
            "snapshot_date",
            "checksum",
            name="uq_universe_snapshot_identity",
        ),
    )
    op.create_index(
        "ix_universe_snapshot_latest",
        "universe_snapshots",
        ["index_code", "fetched_at"],
        unique=False,
    )

    op.create_table(
        "universe_sync_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("index_code", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_count", sa.Integer(), nullable=False),
        sa.Column("normalized_count", sa.Integer(), nullable=False),
        sa.Column("added_count", sa.Integer(), nullable=False),
        sa.Column("removed_count", sa.Integer(), nullable=False),
        sa.Column("unchanged_count", sa.Integer(), nullable=False),
        sa.Column("failed_validation_count", sa.Integer(), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_universe_sync_runs_index_started",
        "universe_sync_runs",
        ["index_code", "started_at"],
        unique=False,
    )

    op.create_table(
        "index_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("index_code", sa.String(length=32), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_snapshot_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "stock_id",
            "index_code",
            "valid_from",
            name="uq_membership_stock_index_from",
        ),
    )
    op.create_index(
        "ix_membership_active",
        "index_memberships",
        ["index_code", "valid_to"],
        unique=False,
    )

    op.create_table(
        "stock_symbol_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("retired_stock_id", sa.Integer(), nullable=True),
        sa.Column("exchange", sa.String(length=16), nullable=False),
        sa.Column("alias_exchange_symbol", sa.String(length=32), nullable=False),
        sa.Column("alias_provider_symbol", sa.String(length=32), nullable=True),
        sa.Column("alias_type", sa.String(length=32), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["retired_stock_id"], ["stocks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "exchange",
            "alias_exchange_symbol",
            name="uq_stock_alias_exchange_symbol",
        ),
    )

    op.create_table(
        "universe_sync_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=True),
        sa.Column("exchange_symbol", sa.String(length=32), nullable=False),
        sa.Column("provider_symbol", sa.String(length=32), nullable=True),
        sa.Column("company_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("validation_status", sa.String(length=32), nullable=True),
        sa.Column("validation_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"], ["universe_sync_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "exchange_symbol", name="uq_sync_item_run_symbol"),
    )
    op.create_index(
        "ix_sync_item_run_status",
        "universe_sync_items",
        ["run_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sync_item_run_status", table_name="universe_sync_items")
    op.drop_table("universe_sync_items")
    op.drop_table("stock_symbol_aliases")
    op.drop_index("ix_membership_active", table_name="index_memberships")
    op.drop_table("index_memberships")
    op.drop_index("ix_universe_sync_runs_index_started", table_name="universe_sync_runs")
    op.drop_table("universe_sync_runs")
    op.drop_index("ix_universe_snapshot_latest", table_name="universe_snapshots")
    op.drop_table("universe_snapshots")
    op.drop_index(op.f("ix_stocks_exchange_symbol"), table_name="stocks")
    op.drop_column("stocks", "data_provider")
    op.drop_column("stocks", "exchange_symbol")
