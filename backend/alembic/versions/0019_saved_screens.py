"""add user-scoped saved screens

Revision ID: 0019_saved_screens
Revises: 0018_strategy_robustness
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_saved_screens"
down_revision: str | None = "0018_strategy_robustness"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saved_screens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("query_text", sa.String(1000), nullable=False),
        sa.Column("filter_ast", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_saved_screens_user_updated", "saved_screens", ["user_id", "updated_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_saved_screens_user_updated", table_name="saved_screens")
    op.drop_table("saved_screens")
