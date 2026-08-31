"""News & sentiment business logic.

Pipeline (deterministic classification, not generation): fetch → dedupe → score
(FinBERT/lexicon) → tag to companies → aggregate daily sentiment per stock. The
aggregate (`sentiment_daily`) is what the history module reads to close Phase 4's
sentiment placeholder.
"""

from __future__ import annotations

import asyncio
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.market.exceptions import SectorNotFoundError, StockNotFoundError
from app.market.repository import MarketRepository
from app.news.classification import (
    classify_event,
    evidence_excerpt,
    sentiment_confidence,
)
from app.news.constants import DEFAULT_FEEDS
from app.news.fingerprints import article_fingerprint
from app.news.models import NewsArticle
from app.news.repository import NewsRepository
from app.news.schemas import (
    ArticleStockMatchOut,
    IngestNewsResult,
    LatestSentimentOut,
    NewsArticleOut,
    NewsDiagnosticsOut,
    SectorSentimentOut,
    SentimentDailyOut,
    StockNewsEvidenceOut,
    StockSentimentOut,
)
from app.news.tagging import build_aliases, match_article_entities
from app.shared.clients.news_client import NewsClient, RssNewsClient
from app.shared.ml.sentiment import SentimentScorer, get_sentiment_scorer
from app.shared.time import utc_now
from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)


class NewsService:
    def __init__(
        self,
        db: AsyncSession,
        scorer: SentimentScorer | None = None,
        client: NewsClient | None = None,
    ) -> None:
        self.db = db
        self.repo = NewsRepository(db)
        self.market = MarketRepository(db)
        self.scorer = scorer or get_sentiment_scorer()
        self.client = client or RssNewsClient(
            list(DEFAULT_FEEDS), max_per_feed=settings.news_max_articles_per_feed
        )

    # ----- Ingestion -------------------------------------------------------
    async def ingest(self) -> IngestNewsResult:
        items = await asyncio.to_thread(self.client.fetch)

        item_keys = [
            (item, article_fingerprint(item.title, item.published_at)) for item in items
        ]
        existing_urls, existing_fingerprints = await self.repo.existing_article_keys(
            [item.url for item, _ in item_keys], [key for _, key in item_keys]
        )
        candidates = [
            (item, key)
            for item, key in item_keys
            if item.url not in existing_urls and key not in existing_fingerprints
        ]
        # Collapse duplicate URLs and cross-feed copies before scoring. The same
        # database keys also arbitrate concurrent ingesters below.
        seen_urls: set[str] = set()
        seen_fingerprints: set[str] = set()
        new_items = []
        for item, key in candidates:
            if item.url in seen_urls or key in seen_fingerprints:
                continue
            seen_urls.add(item.url)
            seen_fingerprints.add(key)
            new_items.append((item, key))

        scores = (
            self.scorer.score([f"{i.title}. {i.summary}" for i, _ in new_items])
            if new_items
            else []
        )

        active = await self.market.list_active_stocks()
        aliases = {s.id: build_aliases(s.symbol, s.name) for s in active}

        inserted = 0
        tagged = 0
        for (item, fingerprint), sc in zip(new_items, scores, strict=True):
            event = classify_event(item.title, item.summary)
            article = NewsArticle(
                source=item.source[:200],
                url=item.url[:1000],
                fingerprint=fingerprint,
                title=item.title[:600],
                summary=item.summary[:4000],
                published_at=item.published_at,
                sentiment_label=sc.label,
                sentiment_score=sc.score,
                sentiment_positive=sc.positive,
                sentiment_negative=sc.negative,
                sentiment_neutral=sc.neutral,
                sentiment_confidence=sentiment_confidence(
                    score=sc.score,
                    positive=sc.positive,
                    negative=sc.negative,
                    neutral=sc.neutral,
                ),
                event_category=event.category,
                event_confidence=event.confidence,
                driver=event.driver,
                evidence_excerpt=evidence_excerpt(item.title, item.summary),
            )
            article_id = await self.repo.add_article(article)
            if article_id is None:
                continue
            inserted += 1
            matches = match_article_entities(item.title, item.summary, aliases)
            for sid, match in matches.items():
                await self.repo.add_tag(
                    article_id,
                    sid,
                    matching_alias=match.alias,
                    entity_match_confidence=match.confidence,
                )
            if matches:
                tagged += 1
        retag_since = utc_now() - timedelta(
            days=settings.news_retag_window_days
        )
        articles_reconciled = 0
        tags_added = 0
        tags_removed = 0
        for article in await self.repo.list_articles_since(retag_since):
            event = classify_event(article.title, article.summary)
            article.event_category = event.category
            article.event_confidence = event.confidence
            article.driver = event.driver
            article.evidence_excerpt = evidence_excerpt(article.title, article.summary)
            article.sentiment_confidence = sentiment_confidence(
                score=article.sentiment_score,
                positive=article.sentiment_positive,
                negative=article.sentiment_negative,
                neutral=article.sentiment_neutral,
            )
            desired = match_article_entities(article.title, article.summary, aliases)
            added, removed = await self.repo.reconcile_tags(
                article,
                {
                    stock_id: (match.alias, match.confidence)
                    for stock_id, match in desired.items()
                },
            )
            if added or removed:
                articles_reconciled += 1
                tags_added += added
                tags_removed += removed
        await self.db.commit()

        days = await self.aggregate()
        logger.info(
            "news_ingest_done",
            extra={
                "fetched": len(items),
                "new": inserted,
                "tagged": tagged,
                "articles_reconciled": articles_reconciled,
                "tags_added": tags_added,
                "tags_removed": tags_removed,
            },
        )
        return IngestNewsResult(
            fetched=len(items),
            new_articles=inserted,
            tagged_articles=tagged,
            articles_reconciled=articles_reconciled,
            tags_added=tags_added,
            tags_removed=tags_removed,
            sentiment_days_updated=days,
        )

    async def aggregate(self) -> int:
        """Recompute per-stock, per-day sentiment from all tagged articles."""
        rows = await self.repo.all_tagged_rows()
        buckets: dict[tuple[int, date], list[tuple[float, str]]] = defaultdict(list)
        for stock_id, published_at, fetched_at, score, label in rows:
            when = published_at or fetched_at
            buckets[(stock_id, when.date())].append((score, label))

        canonical_keys = set(buckets)
        orphan_ids = [
            row_id
            for row_id, stock_id, day in await self.repo.sentiment_row_keys()
            if (stock_id, day) not in canonical_keys
        ]
        await self.repo.delete_sentiment_rows(orphan_ids)

        for (stock_id, day), scored in buckets.items():
            avg = statistics.fmean(s for s, _ in scored)
            pos = sum(1 for _, lbl in scored if lbl == "positive")
            neg = sum(1 for _, lbl in scored if lbl == "negative")
            neu = sum(1 for _, lbl in scored if lbl == "neutral")
            await self.repo.upsert_sentiment_daily(
                stock_id, day, avg=avg, pos=pos, neg=neg, neu=neu
            )
        await self.db.commit()
        return len(buckets)

    # ----- Reads -----------------------------------------------------------
    async def list_recent(self, limit: int = 50) -> list[NewsArticleOut]:
        as_of = await self.market.get_latest_active_price_date() or date.today()
        recent_day = as_of - timedelta(days=settings.news_recent_window_days - 1)
        recent_since = datetime.combine(
            recent_day, datetime.min.time(), tzinfo=timezone.utc
        )
        articles = await self.repo.list_recent_articles(limit, recent_since=recent_since)
        symbols = {s.id: s.symbol for s in await self.market.list_active_stocks()}
        return [
            NewsArticleOut(
                id=a.id,
                source=a.source,
                url=a.url,
                title=a.title,
                summary=a.summary,
                published_at=a.published_at,
                sentiment_label=a.sentiment_label,
                sentiment_score=a.sentiment_score,
                sentiment_confidence=a.sentiment_confidence,
                event_category=a.event_category,
                event_confidence=a.event_confidence,
                driver=a.driver,
                evidence_excerpt=a.evidence_excerpt,
                tags=[symbols[t.stock_id] for t in a.tags if t.stock_id in symbols],
                associations=[
                    ArticleStockMatchOut(
                        symbol=symbols[tag.stock_id],
                        matched_alias=tag.matching_alias,
                        entity_match_confidence=tag.entity_match_confidence,
                    )
                    for tag in a.tags
                    if tag.stock_id in symbols
                ],
            )
            for a in articles
        ]

    async def get_stock_sentiment(self, symbol: str) -> StockSentimentOut:
        stock = await self.market.get_stock_by_symbol(symbol)
        if stock is None:
            raise StockNotFoundError(symbol)
        series = await self.repo.get_sentiment_series(stock.id)
        as_of = await self.market.get_latest_active_price_date() or date.today()
        recent_day = as_of - timedelta(days=settings.news_recent_window_days - 1)
        recent_since = datetime.combine(
            recent_day, datetime.min.time(), tzinfo=timezone.utc
        )
        article_rows = await self.repo.list_recent_stock_articles(
            stock.id, recent_since=recent_since
        )
        evidence = [self._evidence_out(article, association) for article, association in article_rows]
        availability = "available" if evidence else "no_relevant_news"
        latest_sentiment = (
            statistics.fmean(item.sentiment_score for item in evidence)
            if evidence
            else None
        )
        confidence = (
            statistics.fmean(
                item.sentiment_confidence * item.entity_match_confidence
                for item in evidence
            )
            if evidence
            else None
        )
        return StockSentimentOut(
            symbol=stock.symbol,
            name=stock.name,
            latest_sentiment=latest_sentiment,
            availability=availability,
            confidence=confidence,
            article_count=len(evidence),
            positive_count=sum(item.sentiment_class == "positive" for item in evidence),
            negative_count=sum(item.sentiment_class == "negative" for item in evidence),
            neutral_count=sum(item.sentiment_class == "neutral" for item in evidence),
            evidence=evidence,
            series=[
                SentimentDailyOut(
                    date=s.date,
                    avg_sentiment=s.avg_sentiment,
                    article_count=s.article_count,
                    positive_count=s.positive_count,
                    negative_count=s.negative_count,
                    neutral_count=s.neutral_count,
                )
                for s in series
            ],
        )

    async def list_latest_sentiment(self) -> list[LatestSentimentOut]:
        stocks = await self.market.list_active_stocks()
        as_of = await self.market.get_latest_active_price_date() or date.today()
        recent_since = as_of - timedelta(days=settings.news_recent_window_days - 1)
        recent_at = datetime.combine(
            recent_since, datetime.min.time(), tzinfo=timezone.utc
        )
        grouped: dict[int, list[tuple[float, str, float, float]]] = defaultdict(list)
        for stock_id, score, label, article_confidence, entity_confidence in (
            await self.repo.recent_stock_evidence_rows(recent_since=recent_at)
        ):
            grouped[stock_id].append(
                (score, label, article_confidence, entity_confidence)
            )
        return [
            LatestSentimentOut(
                symbol=stock.symbol,
                latest_sentiment=(
                    statistics.fmean(row[0] for row in grouped[stock.id])
                    if grouped.get(stock.id)
                    else None
                ),
                availability=(
                    "available" if grouped.get(stock.id) else "no_relevant_news"
                ),
                confidence=(
                    statistics.fmean(row[2] * row[3] for row in grouped[stock.id])
                    if grouped.get(stock.id)
                    else None
                ),
                article_count=len(grouped.get(stock.id, [])),
            )
            for stock in sorted(stocks, key=lambda item: item.symbol)
        ]

    @staticmethod
    def _evidence_out(article: NewsArticle, association) -> StockNewsEvidenceOut:
        return StockNewsEvidenceOut(
            id=article.id,
            headline=article.title,
            publisher=article.source,
            published_at=article.published_at,
            source_url=article.url,
            sentiment_class=article.sentiment_label,
            sentiment_score=article.sentiment_score,
            sentiment_confidence=article.sentiment_confidence,
            event_category=article.event_category,
            event_confidence=article.event_confidence,
            driver=article.driver,
            evidence_excerpt=article.evidence_excerpt,
            matched_alias=association.matching_alias,
            entity_match_confidence=association.entity_match_confidence,
        )

    async def get_sector_sentiment(self, sector: str) -> SectorSentimentOut:
        if not await self.market.list_stocks_by_sector(sector):
            raise SectorNotFoundError(sector)
        rows = await self.repo.get_sector_sentiment_series(sector)
        series = [
            SentimentDailyOut(
                date=day,
                avg_sentiment=avg,
                article_count=count,
                positive_count=positive,
                negative_count=negative,
                neutral_count=neutral,
            )
            for day, avg, count, positive, negative, neutral in rows
        ]
        return SectorSentimentOut(
            sector=sector,
            latest_sentiment=series[-1].avg_sentiment if series else None,
            series=series,
        )

    async def get_diagnostics(self, recent_window_days: int = 7) -> NewsDiagnosticsOut:
        recent_since = utc_now() - timedelta(days=recent_window_days)
        values = await self.repo.diagnostics(recent_since=recent_since)
        return NewsDiagnosticsOut(recent_window_days=recent_window_days, **values)
