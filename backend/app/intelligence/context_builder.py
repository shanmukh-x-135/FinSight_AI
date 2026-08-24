"""RAG context builder.

Assembles ONLY the relevant slice of already-computed data per request (design
doc §4.6/§5.5) — market analytics, the user's portfolio, historical similarity
statistics, and news sentiment — into a structured ``RagContext``. Nothing here
calls an LLM; it gathers deterministic facts that the prompt builder and
recommendation engine consume.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.history.exceptions import IndexNotBuiltError, SessionNotFoundError
from app.history.service import HistoryService
from app.intelligence.recommendation_engine import CandidateInput
from app.market.repository import MarketRepository
from app.market.service import MarketQueryService
from app.news.repository import NewsRepository
from app.news.service import NewsService
from app.portfolio.repository import PortfolioRepository
from app.portfolio.service import PortfolioService
from config.settings import settings


@dataclass
class RagContext:
    market: dict = field(default_factory=dict)
    portfolio: dict | None = None
    history: dict | None = None
    news: dict = field(default_factory=dict)
    watchlist: list[dict] = field(default_factory=list)
    candidates: list[CandidateInput] = field(default_factory=list)


class ContextBuilder:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.market_repo = MarketRepository(db)
        self.market_q = MarketQueryService(db)
        self.news_repo = NewsRepository(db)
        self.news = NewsService(db)

    # ----- Slices ----------------------------------------------------------
    async def build_market_slice(self) -> dict:
        breadth, gainers, losers = await self.market_q.get_market_overview(5)
        return {
            "breadth": breadth.model_dump(mode="json"),
            "gainers": [g.model_dump(mode="json") for g in gainers],
            "losers": [x.model_dump(mode="json") for x in losers],
        }

    async def build_history_slice(self) -> dict | None:
        try:
            result = await HistoryService(self.db).query_similar(k=5)
        except (IndexNotBuiltError, SessionNotFoundError):
            return None
        return {
            "query_date": result.query_date.isoformat(),
            "query_summary": result.query_summary.model_dump(mode="json"),
            "similar_sessions": [
                s.model_dump(mode="json") for s in result.similar_sessions
            ],
            "statistics": result.statistics.model_dump(mode="json"),
        }

    async def build_portfolio_slice(self, user_id: int | None) -> dict | None:
        if user_id is None:
            return None
        portfolios = await PortfolioRepository(self.db).list_portfolios(user_id)
        if not portfolios:
            return None
        analytics = await PortfolioService(self.db).get_analytics(
            user_id, portfolios[0].id
        )
        return analytics.model_dump(mode="json")

    async def build_news_slice(self) -> dict:
        articles = await self.news.list_recent(10)
        notable = [
            {
                "title": a.title,
                "sentiment_label": a.sentiment_label,
                "sentiment_score": a.sentiment_score,
                "tags": a.tags,
            }
            for a in articles
            if a.tags  # only company-tagged articles are "notable"
        ][:5]
        return {"notable": notable}

    async def build_watchlist_slice(self, user_id: int) -> list[dict]:
        """Return the authenticated user's quote-enriched watchlist facts."""
        items = await PortfolioService(self.db).list_watchlist(user_id)
        return [item.model_dump(mode="json") for item in items]

    async def build_candidates(self, history_slice: dict | None) -> list[CandidateInput]:
        stocks = await self.market_repo.list_active_stocks()
        as_of = await self.market_repo.get_latest_active_price_date() or date.today()
        recent_since = as_of - timedelta(days=settings.news_recent_window_days - 1)
        sentiment_map = await self.news_repo.get_latest_sentiment_map(
            recent_since=recent_since
        )
        snapshots = await self.market_repo.get_market_snapshots(
            (stock.id for stock in stocks), known_stocks=stocks
        )

        # First pass: day quotes, to compute sector momentum.
        quotes: dict[int, tuple] = {}
        for s in stocks:
            snapshot = snapshots.get(s.id)
            prices = snapshot.prices if snapshot else ()
            if not prices:
                continue
            latest = prices[0]
            prev = prices[1] if len(prices) > 1 else None
            change = (
                (latest.close - prev.close) / prev.close * 100
                if prev and prev.close
                else None
            )
            quotes[s.id] = (s, latest.close, change)

        sector_changes: dict[str, list[float]] = {}
        for s, _price, change in quotes.values():
            if s.sector and change is not None:
                sector_changes.setdefault(s.sector, []).append(change)
        sector_avg = {sec: statistics.fmean(v) for sec, v in sector_changes.items()}

        bull_prob = sample = None
        if history_slice:
            stats = history_slice["statistics"]
            bull_prob = stats.get("bullish_probability")
            sample = stats.get("sample_size")

        candidates: list[CandidateInput] = []
        for stock_id, (s, price, change) in quotes.items():
            ind = snapshots[stock_id].indicator
            ema20_dist = (
                (price - ind.ema_20) / ind.ema_20 * 100 if ind and ind.ema_20 else None
            )
            ema50_dist = (
                (price - ind.ema_50) / ind.ema_50 * 100 if ind and ind.ema_50 else None
            )
            atr_pct = (ind.atr_14 / price * 100) if ind and ind.atr_14 and price else None
            candidates.append(
                CandidateInput(
                    symbol=s.symbol,
                    name=s.name,
                    sector=s.sector,
                    price=price,
                    change_percent=change,
                    rsi=ind.rsi_14 if ind else None,
                    ema20_distance_pct=ema20_dist,
                    ema50_distance_pct=ema50_dist,
                    macd_hist=ind.macd_histogram if ind else None,
                    atr_pct=atr_pct,
                    sentiment=sentiment_map.get(stock_id),
                    sector_change_percent=sector_avg.get(s.sector) if s.sector else None,
                    hist_bullish_probability=bull_prob,
                    hist_sample_size=sample,
                )
            )
        return candidates

    # ----- Composition -----------------------------------------------------
    async def build_report_context(self, user_id: int | None) -> RagContext:
        history = await self.build_history_slice()
        return RagContext(
            market=await self.build_market_slice(),
            portfolio=await self.build_portfolio_slice(user_id),
            history=history,
            news=await self.build_news_slice(),
            candidates=await self.build_candidates(history),
        )

    async def build_chat_context(self, user_id: int) -> RagContext:
        """Compose the user-scoped slices available to conversational Q&A."""
        history = await self.build_history_slice()
        return RagContext(
            market=await self.build_market_slice(),
            portfolio=await self.build_portfolio_slice(user_id),
            history=history,
            news=await self.build_news_slice(),
            watchlist=await self.build_watchlist_slice(user_id),
        )
