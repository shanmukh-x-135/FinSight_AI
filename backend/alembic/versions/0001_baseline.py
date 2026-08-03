"""baseline (empty)

The initial migration intentionally creates no tables. It exists to prove the
Alembic pipeline works end-to-end (design doc §6.9 / Phase 0) and to give later
phases a parent revision to build on. Domain tables arrive from Phase 1.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-04
"""
from __future__ import annotations

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No-op baseline. Domain tables are introduced in later phases.
    pass


def downgrade() -> None:
    pass
