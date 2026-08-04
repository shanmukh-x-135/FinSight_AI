"""ORM models for the news domain.

* **NewsArticle**      — a deduped article (by URL) with its FinBERT/lexicon
  sentiment scores.
* **NewsArticleStock** — company tags: which tracked stocks an article mentions.
* **SentimentDaily**   — per-stock, per-day aggregated sentiment. This is the
  read surface consumed by the market and history modules (it closes Phase 4's
  sentiment placeholder).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.database import Base


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(600), nullable=False)
    summary: Mapped[str] = mapped_column(String(4000), default="", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sentiment_label: Mapped[str] = mapped_column(String(10), nullable=False)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False)   # [-1, 1]
    sentiment_positive: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sentiment_negative: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sentiment_neutral: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )

    tags: Mapped[list["NewsArticleStock"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )


class NewsArticleStock(Base):
    __tablename__ = "news_article_stocks"
    __table_args__ = (
        UniqueConstraint("article_id", "stock_id", name="uq_news_article_stock"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("news_articles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), index=True, nullable=False
    )

    article: Mapped["NewsArticle"] = relationship(back_populates="tags")


class SentimentDaily(Base):
    __tablename__ = "sentiment_daily"
    __table_args__ = (
        UniqueConstraint("stock_id", "date", name="uq_sentiment_daily_stock_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    avg_sentiment: Mapped[float] = mapped_column(Float, nullable=False)
    article_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    positive_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    negative_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    neutral_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )
