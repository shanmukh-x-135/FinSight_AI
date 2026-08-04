"""News dependencies — isolate the news source and scorer so tests can inject
fakes (no network, no model)."""

from __future__ import annotations

from app.news.constants import DEFAULT_FEEDS
from app.shared.clients.news_client import NewsClient, RssNewsClient
from app.shared.ml.sentiment import SentimentScorer, get_sentiment_scorer
from config.settings import settings


def get_news_client() -> NewsClient:
    return RssNewsClient(list(DEFAULT_FEEDS), max_per_feed=settings.news_max_articles_per_feed)


def get_news_scorer() -> SentimentScorer:
    return get_sentiment_scorer()
