"""freeze the pre-Phase-10C historical reconstruction universe

Revision ID: 0014_freeze_history_universe
Revises: 0013_dynamic_universe
Create Date: 2026-08-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_freeze_history_universe"
down_revision: str | None = "0013_dynamic_universe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "stocks",
        sa.Column(
            "history_eligible",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    # Capture the legacy tracked equity set once. Later NIFTY membership changes
    # must not retroactively alter historical feature reconstruction in Phase 10C.
    op.execute("UPDATE stocks SET history_eligible = is_active")


def downgrade() -> None:
    op.drop_column("stocks", "history_eligible")
