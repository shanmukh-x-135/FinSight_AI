"""Report generator — assembles the structured, evidence-backed report.

Deterministic facts (analytics, rankings, evidence, confidence, risks) are built
first; the LLM only writes the prose narratives over them. The result is
validated for explainability before it is returned/stored.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence import prompt_builder as pb
from app.intelligence.context_builder import ContextBuilder, RagContext
from app.intelligence.explainability import validate_report
from app.intelligence.generation import (
    GenerationBudget,
    backend_label,
    generation_record,
    summarize_generations,
)
from app.intelligence.llm_client import (
    LLMClient,
    generate_grounded_result,
    get_llm_client,
)
from app.intelligence.recommendation_engine import (
    Recommendation,
    rank_candidates,
    select_risk_alerts,
    select_watchlist,
)
from app.shared.time import utc_now
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

    async def _narrate(
        self,
        purpose: str,
        prompt_fallback: tuple[str, str],
        budget: GenerationBudget,
    ) -> tuple[str, dict]:
        prompt, fallback = prompt_fallback
        result = await generate_grounded_result(
            self.llm, self.system, prompt, fallback, budget=budget
        )
        return result.text, generation_record(purpose, result.metadata)

    async def generate(self, user_id: int | None) -> dict:
        generation_records: list[dict] = []
        budget = GenerationBudget(
            settings.llm_request_budget_seconds,
            settings.llm_max_provider_calls,
        )
        ctx: RagContext = await ContextBuilder(self.db).build_report_context(user_id)
        sections: dict = {}

        ranked = rank_candidates(ctx.candidates)
        watchlist = select_watchlist(ranked, settings.top_n_recommendations)
        risk_alerts = select_risk_alerts(ranked)

        requests: list[tuple[str, tuple[str, str]]] = [
            ("market_summary", pb.market_section(ctx.market))
        ]
        if ctx.history:
            requests.append(("historical_summary", pb.historical_section(ctx.history)))
        if ctx.portfolio:
            requests.append(("portfolio_summary", pb.portfolio_section(ctx.portfolio)))
        requests.extend(
            (
                f"recommendation:{rec.symbol}",
                pb.recommendation_explanation(rec),
            )
            for rec in watchlist + risk_alerts
        )
        generated = await asyncio.gather(
            *(self._narrate(purpose, content, budget) for purpose, content in requests)
        )
        narratives = {
            purpose: result[0]
            for (purpose, _), result in zip(requests, generated, strict=True)
        }
        generation_records.extend(result[1] for result in generated)

        # Market
        sections["market_summary"] = {
            "narrative": narratives["market_summary"],
            "breadth": ctx.market["breadth"],
            "gainers": ctx.market["gainers"],
            "losers": ctx.market["losers"],
        }

        # Historical (optional — only if the index is built)
        if ctx.history:
            sections["historical_summary"] = {
                "narrative": narratives["historical_summary"],
                "query_date": ctx.history["query_date"],
                "statistics": ctx.history["statistics"],
                "similar_sessions": ctx.history["similar_sessions"],
            }

        # Portfolio (optional — only if the user has one)
        if ctx.portfolio:
            sections["portfolio_summary"] = {
                "narrative": narratives["portfolio_summary"],
                **{
                    k: ctx.portfolio[k]
                    for k in (
                        "total_value",
                        "total_return_percent",
                        "health_score",
                        "risk_level",
                        "diversification_score",
                        "number_of_holdings",
                        "sector_allocation",
                        "valuation_complete",
                        "unpriced_symbols",
                        "total_cost",
                    )
                },
            }

        # Recommendations (deterministic ranking; LLM only explains)
        for rec in watchlist + risk_alerts:
            rec.explanation = narratives[f"recommendation:{rec.symbol}"]
        sections["recommendations"] = [_rec_to_dict(r) for r in watchlist]
        sections["risk_alerts"] = [_rec_to_dict(r) for r in risk_alerts]

        sections["news"] = ctx.news

        # Executive summary (last — synthesizes the above)
        executive, executive_record = await self._narrate(
            "executive_summary", pb.executive_summary(sections), budget
        )
        sections["executive_summary"] = executive
        generation_records.append(executive_record)

        generation = summarize_generations(
            generation_records,
            configured_backend=type(self.llm).__name__,
        )
        sections["meta"] = {
            "prompt_version": PROMPT_VERSION,
            "llm_backend": backend_label(generation),
            "generation": generation,
            "generated_at": utc_now().isoformat(),
        }

        validate_report(sections)
        return sections
