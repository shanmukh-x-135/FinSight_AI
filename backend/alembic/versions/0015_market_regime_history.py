"""version historical sessions for market-regime reconstruction

Revision ID: 0015_market_regime_history
Revises: 0014_freeze_history_universe
Create Date: 2026-08-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_market_regime_history"
down_revision: str | None = "0014_freeze_history_universe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_FEATURE_VERSION = "legacy_market_v1"
LEGACY_NORMALIZATION = "zscore_v1"


def upgrade() -> None:
    op.add_column(
        "historical_sessions",
        sa.Column(
            "feature_version",
            sa.String(length=32),
            server_default=LEGACY_FEATURE_VERSION,
            nullable=False,
        ),
    )
    op.add_column(
        "historical_sessions",
        sa.Column("feature_dimension", sa.Integer(), server_default="15", nullable=False),
    )
    op.add_column(
        "historical_sessions",
        sa.Column(
            "usable_constituent_count", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "historical_sessions",
        sa.Column(
            "expected_constituent_count", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "historical_sessions",
        sa.Column("coverage_ratio", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "historical_sessions",
        sa.Column(
            "sector_coverage_ratio", sa.Float(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "historical_sessions",
        sa.Column(
            "membership_mode",
            sa.String(length=32),
            server_default="legacy_frozen",
            nullable=False,
        ),
    )
    op.add_column(
        "historical_sessions",
        sa.Column(
            "quality_flags",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
    )
    op.add_column(
        "historical_sessions",
        sa.Column("next_session_breadth", sa.Float(), nullable=True),
    )
    op.add_column(
        "historical_sessions",
        sa.Column("forward_5_session_return", sa.Float(), nullable=True),
    )
    op.add_column(
        "historical_sessions",
        sa.Column("forward_5_session_drawdown", sa.Float(), nullable=True),
    )
    op.add_column(
        "historical_sessions",
        sa.Column("forward_5_session_upside", sa.Float(), nullable=True),
    )
    op.add_column(
        "historical_embeddings",
        sa.Column(
            "feature_version",
            sa.String(length=32),
            server_default=LEGACY_FEATURE_VERSION,
            nullable=False,
        ),
    )
    op.add_column(
        "historical_index_state",
        sa.Column(
            "feature_version",
            sa.String(length=32),
            server_default=LEGACY_FEATURE_VERSION,
            nullable=False,
        ),
    )
    op.add_column(
        "historical_index_state",
        sa.Column(
            "normalization_method",
            sa.String(length=32),
            server_default=LEGACY_NORMALIZATION,
            nullable=False,
        ),
    )

    # Legacy vectors remain inspectable but cannot be queried as the new regime
    # representation. Rebuild atomically replaces them and creates v1 state.
    op.execute("DELETE FROM historical_statistics")
    op.execute("DELETE FROM historical_embeddings")
    op.execute("DELETE FROM historical_index_state")


def downgrade() -> None:
    # New regime vectors must never be interpreted by the legacy 15-feature code.
    op.execute("DELETE FROM historical_statistics")
    op.execute("DELETE FROM historical_embeddings")
    op.execute("DELETE FROM historical_index_state")
    op.drop_column("historical_index_state", "normalization_method")
    op.drop_column("historical_index_state", "feature_version")
    op.drop_column("historical_embeddings", "feature_version")
    op.drop_column("historical_sessions", "forward_5_session_upside")
    op.drop_column("historical_sessions", "forward_5_session_drawdown")
    op.drop_column("historical_sessions", "forward_5_session_return")
    op.drop_column("historical_sessions", "next_session_breadth")
    op.drop_column("historical_sessions", "quality_flags")
    op.drop_column("historical_sessions", "membership_mode")
    op.drop_column("historical_sessions", "sector_coverage_ratio")
    op.drop_column("historical_sessions", "coverage_ratio")
    op.drop_column("historical_sessions", "expected_constituent_count")
    op.drop_column("historical_sessions", "usable_constituent_count")
    op.drop_column("historical_sessions", "feature_dimension")
    op.drop_column("historical_sessions", "feature_version")
