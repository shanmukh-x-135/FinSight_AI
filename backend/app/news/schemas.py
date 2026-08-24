"""Pydantic schemas for the news & sentiment endpoints."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class NewsArticleOut(BaseModel):
    id: int
    source: str
    url: str
    title: str
    summary: str
    published_at: datetime | None
    sentiment_label: str
    sentiment_score: float
    tags: list[str]


class SentimentDailyOut(BaseModel):
    date: date
    avg_sentiment: float
    article_count: int
    positive_count: int
    negative_count: int
    neutral_count: int


class StockSentimentOut(BaseModel):
    symbol: str
    name: str | None
    latest_sentiment: float | None
    series: list[SentimentDailyOut]


class LatestSentimentOut(BaseModel):
    symbol: str
    latest_sentiment: float | None


class SectorSentimentOut(BaseModel):
    sector: str
    latest_sentiment: float | None
    series: list[SentimentDailyOut]


class IngestNewsResult(BaseModel):
    fetched: int
    new_articles: int
    tagged_articles: int
    articles_reconciled: int
    tags_added: int
    tags_removed: int
    sentiment_days_updated: int


class NewsDiagnosticsOut(BaseModel):
    recent_window_days: int
    total_articles: int
    recent_articles: int
    linked_articles: int
    article_stock_associations: int
    distinct_active_stocks_with_links: int
    sentiment_rows: int
    positive_articles: int
    neutral_articles: int
    negative_articles: int
    active_stocks_with_recent_sentiment: int
    latest_news_ingestion_at: datetime | None
    latest_sentiment_at: datetime | None
