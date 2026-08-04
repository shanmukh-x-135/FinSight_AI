"""Dashboard aggregation service (Phase 7).

Read-only: it composes already-computed analytics and Phase 6's deterministic
recommendation engine into one payload so the home screen needs a single
request instead of five. No new intelligence is generated here — the AI market
summary and recommendation explanations come from the same narrator/LLM path
used by report generation, and the rankings/evidence remain deterministic.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence import prompt_builder as pb
from app.intelligence.context_builder import ContextBuilder
from app.intelligence.llm_client import LLMClient, get_llm_client
from app.intelligence.recommendation_engine import (
    rank_candidates,
    select_risk_alerts,
    select_watchlist,
)
from app.intelligence.report_generator import _rec_to_dict
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

        # Recommendations: deterministic ranking; the LLM only explains each pick.
        candidates = await self.cb.build_candidates(history)
        ranked = rank_candidates(candidates)
        watchlist = select_watchlist(ranked, settings.top_n_recommendations)
        risk_alerts = select_risk_alerts(ranked)

        system = pb.system_instruction()
        for rec in watchlist + risk_alerts:
            prompt, fallback = pb.recommendation_explanation(rec)
            rec.explanation = await self.llm.generate(system, prompt, fallback)

        market_prompt, market_fallback = pb.market_section(market)
        ai_market_summary = await self.llm.generate(
            system, market_prompt, market_fallback
        )

        return {
            "market": market,
            "ai_market_summary": ai_market_summary,
            "portfolio": portfolio,
            "opportunities": [_rec_to_dict(r) for r in watchlist],
            "risk_alerts": [_rec_to_dict(r) for r in risk_alerts],
            "history": history,
        }
