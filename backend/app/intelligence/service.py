"""Intelligence service — orchestrates report generation and recommendations."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence import prompt_builder as pb
from app.intelligence.context_builder import ContextBuilder
from app.intelligence.llm_client import LLMClient, generate_grounded, get_llm_client
from app.intelligence.models import Report
from app.intelligence.recommendation_engine import (
    rank_candidates,
    select_risk_alerts,
    select_watchlist,
)
from app.intelligence.report_generator import ReportGenerator, _rec_to_dict
from app.reports.idempotency import scope_idempotency_key
from app.reports.repository import ReportRepository
from config.settings import settings


class IntelligenceService:
    def __init__(self, db: AsyncSession, llm: LLMClient | None = None) -> None:
        self.db = db
        self.llm = llm or get_llm_client()
        self.report_repo = ReportRepository(db)

    async def generate_report(
        self,
        user_id: int | None,
        report_type: str = "daily",
        *,
        idempotency_key: str | None = None,
    ) -> Report:
        key_hash = (
            scope_idempotency_key(user_id, report_type, idempotency_key)
            if idempotency_key is not None
            else None
        )
        if key_hash is not None:
            existing = await self.report_repo.get_by_idempotency_hash(key_hash)
            if existing is not None:
                return existing

        sections = await ReportGenerator(self.db, self.llm).generate(user_id)
        report = await self.report_repo.create_report(
            user_id,
            report_type,
            sections,
            idempotency_key_hash=key_hash,
        )
        await self.db.commit()
        return report

    async def get_recommendations(self, user_id: int | None) -> dict:
        cb = ContextBuilder(self.db)
        history = await cb.build_history_slice()
        candidates = await cb.build_candidates(history)

        ranked = rank_candidates(candidates)
        watchlist = select_watchlist(ranked, settings.top_n_recommendations)
        risk_alerts = select_risk_alerts(ranked)
        system = pb.system_instruction()
        for rec in watchlist + risk_alerts:
            prompt, fallback = pb.recommendation_explanation(rec)
            rec.explanation = await generate_grounded(
                self.llm, system, prompt, fallback
            )
        return {
            "watchlist": [_rec_to_dict(r) for r in watchlist],
            "risk_alerts": [_rec_to_dict(r) for r in risk_alerts],
        }
