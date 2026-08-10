"""add news fingerprints and report idempotency keys

Revision ID: 0010_write_idempotency
Revises: 0009_pipeline_control
Create Date: 2026-08-10
"""

from __future__ import annotations

import hashlib
import re
import statistics
import unicodedata
from collections import defaultdict
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_write_idempotency"
down_revision: str | None = "0009_pipeline_control"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _fingerprint(title: str, published_at: object | None) -> str:
    normalized = unicodedata.normalize("NFKC", title).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE).strip()
    day = published_at.date().isoformat() if hasattr(published_at, "date") else "unknown"
    return hashlib.sha256(f"{day}\n{normalized}".encode()).hexdigest()


def upgrade() -> None:
    op.add_column(
        "news_articles", sa.Column("fingerprint", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "reports", sa.Column("idempotency_key_hash", sa.String(length=64), nullable=True)
    )

    bind = op.get_bind()
    metadata = sa.MetaData()
    articles = sa.Table("news_articles", metadata, autoload_with=bind)
    tags = sa.Table("news_article_stocks", metadata, autoload_with=bind)
    sentiment_daily = sa.Table("sentiment_daily", metadata, autoload_with=bind)

    canonical_by_fingerprint: dict[str, int] = {}
    rows = bind.execute(
        sa.select(
            articles.c.id,
            articles.c.title,
            articles.c.published_at,
        ).order_by(articles.c.id)
    ).all()
    for article_id, title, published_at in rows:
        fingerprint = _fingerprint(title, published_at)
        canonical_id = canonical_by_fingerprint.get(fingerprint)
        if canonical_id is None:
            canonical_by_fingerprint[fingerprint] = article_id
            bind.execute(
                articles.update()
                .where(articles.c.id == article_id)
                .values(fingerprint=fingerprint)
            )
            continue

        stock_ids = bind.execute(
            sa.select(tags.c.stock_id).where(tags.c.article_id == article_id)
        ).scalars()
        existing_stock_ids = set(
            bind.execute(
                sa.select(tags.c.stock_id).where(tags.c.article_id == canonical_id)
            ).scalars()
        )
        for stock_id in stock_ids:
            if stock_id not in existing_stock_ids:
                bind.execute(tags.insert().values(article_id=canonical_id, stock_id=stock_id))
        bind.execute(tags.delete().where(tags.c.article_id == article_id))
        bind.execute(articles.delete().where(articles.c.id == article_id))

    # Removing an already-counted duplicate must also repair the materialized
    # daily aggregate in the same migration transaction.
    buckets: dict[tuple[int, object], list[tuple[float, str]]] = defaultdict(list)
    tagged_rows = bind.execute(
        sa.select(
            tags.c.stock_id,
            articles.c.published_at,
            articles.c.fetched_at,
            articles.c.sentiment_score,
            articles.c.sentiment_label,
        ).join(articles, articles.c.id == tags.c.article_id)
    ).all()
    for stock_id, published_at, fetched_at, score, label in tagged_rows:
        buckets[(stock_id, (published_at or fetched_at).date())].append((score, label))
    bind.execute(sentiment_daily.delete())
    for (stock_id, day), scored in buckets.items():
        bind.execute(
            sentiment_daily.insert().values(
                stock_id=stock_id,
                date=day,
                avg_sentiment=statistics.fmean(score for score, _ in scored),
                article_count=len(scored),
                positive_count=sum(label == "positive" for _, label in scored),
                negative_count=sum(label == "negative" for _, label in scored),
                neutral_count=sum(label == "neutral" for _, label in scored),
            )
        )

    op.alter_column(
        "news_articles",
        "fingerprint",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.create_index(
        "ix_news_articles_fingerprint",
        "news_articles",
        ["fingerprint"],
        unique=True,
    )
    op.create_index(
        "ix_reports_idempotency_key_hash",
        "reports",
        ["idempotency_key_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_reports_idempotency_key_hash", table_name="reports")
    op.drop_column("reports", "idempotency_key_hash")
    op.drop_index("ix_news_articles_fingerprint", table_name="news_articles")
    op.drop_column("news_articles", "fingerprint")
