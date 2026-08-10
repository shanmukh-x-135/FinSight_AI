"""add per-symbol full price synchronization watermark

Revision ID: 0011_incremental_ingestion
Revises: 0010_write_idempotency
Create Date: 2026-08-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_incremental_ingestion"
down_revision: str | None = "0010_write_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "stocks",
        sa.Column("last_full_price_sync_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("stocks", "last_full_price_sync_at")
