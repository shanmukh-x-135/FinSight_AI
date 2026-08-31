"""add evidence-backed news metadata

Revision ID: 0016_news_evidence
Revises: 0015_market_regime_history
Create Date: 2026-08-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_news_evidence"
down_revision: str | None = "0015_market_regime_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("news_articles", sa.Column("sentiment_confidence", sa.Float(), server_default="0", nullable=False))
    op.add_column("news_articles", sa.Column("event_category", sa.String(length=32), server_default="Other", nullable=False))
    op.add_column("news_articles", sa.Column("event_confidence", sa.Float(), server_default="0", nullable=False))
    op.add_column("news_articles", sa.Column("driver", sa.String(length=240), server_default="Unclassified company coverage", nullable=False))
    op.add_column("news_articles", sa.Column("evidence_excerpt", sa.String(length=600), server_default="", nullable=False))
    op.execute("UPDATE news_articles SET evidence_excerpt = LEFT(title, 600) WHERE evidence_excerpt = ''")
    op.add_column("news_article_stocks", sa.Column("matching_alias", sa.String(length=160), nullable=True))
    op.add_column("news_article_stocks", sa.Column("entity_match_confidence", sa.Float(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("news_article_stocks", "entity_match_confidence")
    op.drop_column("news_article_stocks", "matching_alias")
    op.drop_column("news_articles", "evidence_excerpt")
    op.drop_column("news_articles", "driver")
    op.drop_column("news_articles", "event_confidence")
    op.drop_column("news_articles", "event_category")
    op.drop_column("news_articles", "sentiment_confidence")
