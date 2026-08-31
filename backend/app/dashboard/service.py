"""Dashboard aggregation service (Phase 7).

Read-only: it composes already-computed analytics and Phase 6's deterministic
recommendation engine into one payload so the home screen needs a single
request instead of five. No new intelligence is generated here — the AI market
summary and recommendation explanations come from the same narrator/LLM path
used by report generation, and the rankings/evidence remain deterministic.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.dashboard.freshness import FreshnessService
from app.intelligence import prompt_builder as pb
from app.intelligence.context_builder import ContextBuilder
from app.intelligence.generation import (
    GenerationBudget,
    generation_record,
    summarize_generations,
)
from app.intelligence.llm_client import (
    LLMClient,
    generate_grounded_result,
    get_llm_client,
)
from app.intelligence.recommendation_engine import (
    rank_candidates,
    select_risk_alerts,
    select_watchlist,
)
from app.intelligence.report_generator import _rec_to_dict
from app.market.service import MarketQueryService
from app.news.service import NewsService
from app.portfolio.service import PortfolioService
from config.settings import settings


class DashboardService:
    def __init__(self, db: AsyncSession, llm: LLMClient | None = None) -> None:
        self.db = db
        self.cb = ContextBuilder(db)
        self.llm = llm or get_llm_client()

    async def build_summary(self, user_id: int | None) -> dict:
        market = await self.cb.build_market_slice()
        history = await self.cb.build_history_slice()
        portfolio = await self.cb.build_portfolio_slice(user_id)
        user_watchlist = (
            await PortfolioService(self.db).list_watchlist(user_id)
            if user_id is not None
            else []
        )
        market_queries = MarketQueryService(self.db)
        sectors = await market_queries.get_sectors_overview()
        technical = await market_queries.get_technical_summary()
        sentiment = await NewsService(self.db).list_latest_sentiment()
        freshness = await FreshnessService(self.db).get()

        # Recommendations: deterministic ranking; the LLM only explains each pick.
        candidates = await self.cb.build_candidates(history)
        ranked = rank_candidates(candidates)
        opportunities = select_watchlist(ranked, settings.top_n_recommendations)
        risk_alerts = select_risk_alerts(ranked)

        system = pb.system_instruction()
        recommendations = opportunities + risk_alerts
        budget = GenerationBudget(
            settings.llm_request_budget_seconds,
            settings.llm_max_provider_calls,
        )

        async def narrate_recommendation(rec):
            prompt, fallback = pb.recommendation_explanation(rec)
            return await generate_grounded_result(
                self.llm, system, prompt, fallback, budget=budget
            )

        market_prompt, market_fallback = pb.market_section(market)
        generated = await asyncio.gather(
            *(narrate_recommendation(rec) for rec in recommendations),
            generate_grounded_result(
                self.llm,
                system,
                market_prompt,
                market_fallback,
                budget=budget,
            ),
        )

        generation_records: list[dict] = []
        for rec, result in zip(recommendations, generated[:-1], strict=True):
            rec.explanation = result.text
            generation_records.append(
                generation_record(f"recommendation:{rec.symbol}", result.metadata)
            )

        market_result = generated[-1]
        generation_records.append(
            generation_record("market_summary", market_result.metadata)
        )

        return {
            "market": market,
            "ai_market_summary": market_result.text,
            "portfolio": portfolio,
            "watchlist": [item.model_dump(mode="json") for item in user_watchlist],
            "sectors": [item.model_dump(mode="json") for item in sectors],
            "technical": technical.model_dump(mode="json"),
            "sentiment": [item.model_dump(mode="json") for item in sentiment],
            "opportunities": [_rec_to_dict(r) for r in opportunities],
            "risk_alerts": [_rec_to_dict(r) for r in risk_alerts],
            "history": history,
            "generation": summarize_generations(
                generation_records,
                configured_backend=type(self.llm).__name__,
            ),
            "freshness": [item.model_dump(mode="json") for item in freshness],
        }
