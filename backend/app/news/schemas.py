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
    sentiment_days_updated: int
