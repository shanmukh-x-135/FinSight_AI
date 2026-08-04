"""Report generator — assembles the structured, evidence-backed report.

Deterministic facts (analytics, rankings, evidence, confidence, risks) are built
first; the LLM only writes the prose narratives over them. The result is
validated for explainability before it is returned/stored.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence import prompt_builder as pb
from app.intelligence.context_builder import ContextBuilder, RagContext
from app.intelligence.explainability import validate_report
from app.intelligence.llm_client import LLMClient, get_llm_client
from app.intelligence.recommendation_engine import (
    Recommendation,
    rank_candidates,
    select_risk_alerts,
    select_watchlist,
)
from config.prompts import PROMPT_VERSION
from config.settings import settings


def _rec_to_dict(rec: Recommendation) -> dict:
    return {
        "symbol": rec.symbol,
        "name": rec.name,
        "sector": rec.sector,
        "action": rec.action,
        "confidence": rec.confidence,
        "score": rec.score,
        "evidence": rec.evidence,
        "risks": rec.risks,
        "historical_context": rec.historical_context,
        "explanation": rec.explanation,
    }


class ReportGenerator:
    def __init__(self, db: AsyncSession, llm: LLMClient | None = None) -> None:
        self.db = db
        self.llm = llm or get_llm_client()
        self.system = pb.system_instruction()

    def _narrate(self, prompt_fallback: tuple[str, str]) -> str:
        prompt, fallback = prompt_fallback
        return self.llm.generate(self.system, prompt, fallback)

    async def generate(self, user_id: int | None) -> dict:
        ctx: RagContext = await ContextBuilder(self.db).build_report_context(user_id)
        sections: dict = {}

        # Market
        prompt, fallback = pb.market_section(ctx.market)
        sections["market_summary"] = {
            "narrative": self._narrate((prompt, fallback)),
            "breadth": ctx.market["breadth"],
            "gainers": ctx.market["gainers"],
            "losers": ctx.market["losers"],
        }

        # Historical (optional — only if the index is built)
        if ctx.history:
            prompt, fallback = pb.historical_section(ctx.history)
            sections["historical_summary"] = {
                "narrative": self._narrate((prompt, fallback)),
                "query_date": ctx.history["query_date"],
                "statistics": ctx.history["statistics"],
                "similar_sessions": ctx.history["similar_sessions"],
            }

        # Portfolio (optional — only if the user has one)
        if ctx.portfolio:
            prompt, fallback = pb.portfolio_section(ctx.portfolio)
            sections["portfolio_summary"] = {
                "narrative": self._narrate((prompt, fallback)),
                **{
                    k: ctx.portfolio[k]
                    for k in (
                        "total_value", "total_return_percent", "health_score",
                        "risk_level", "diversification_score", "number_of_holdings",
                        "sector_allocation",
                    )
                },
            }

        # Recommendations (deterministic ranking; LLM only explains)
        ranked = rank_candidates(ctx.candidates)
        watchlist = select_watchlist(ranked, settings.top_n_recommendations)
        risk_alerts = select_risk_alerts(ranked)
        for rec in watchlist + risk_alerts:
            rec.explanation = self._narrate(pb.recommendation_explanation(rec))
        sections["recommendations"] = [_rec_to_dict(r) for r in watchlist]
        sections["risk_alerts"] = [_rec_to_dict(r) for r in risk_alerts]

        sections["news"] = ctx.news

        # Executive summary (last — synthesizes the above)
        sections["executive_summary"] = self._narrate(pb.executive_summary(sections))

        sections["meta"] = {
            "prompt_version": PROMPT_VERSION,
            "llm_backend": type(self.llm).__name__,
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        }

        validate_report(sections)
        return sections
