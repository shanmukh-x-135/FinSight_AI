"""persist deterministic strategy robustness analysis

Revision ID: 0018_strategy_robustness
Revises: 0017_strategy_backtesting
Create Date: 2026-08-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_strategy_robustness"
down_revision: str | None = "0017_strategy_backtesting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("backtest_runs", sa.Column("robustness_analysis", sa.JSON()))


def downgrade() -> None:
    op.drop_column("backtest_runs", "robustness_analysis")
