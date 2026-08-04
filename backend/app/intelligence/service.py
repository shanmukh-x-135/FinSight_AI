"""Intelligence service — orchestrates report generation and recommendations."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence import prompt_builder as pb
from app.intelligence.context_builder import ContextBuilder
from app.intelligence.exceptions import ReportNotFoundError
from app.intelligence.llm_client import LLMClient, get_llm_client
from app.intelligence.models import Report
from app.intelligence.recommendation_engine import (
    rank_candidates,
    select_risk_alerts,
    select_watchlist,
)
from app.intelligence.report_generator import ReportGenerator, _rec_to_dict
from app.intelligence.repository import IntelligenceRepository
from config.settings import settings


class IntelligenceService:
    def __init__(self, db: AsyncSession, llm: LLMClient | None = None) -> None:
        self.db = db
        self.llm = llm or get_llm_client()
        self.repo = IntelligenceRepository(db)

    async def generate_report(
        self, user_id: int | None, report_type: str = "daily"
    ) -> Report:
        sections = await ReportGenerator(self.db, self.llm).generate(user_id)
        report = await self.repo.create_report(user_id, report_type, sections)
        await self.db.commit()
        return report

    async def get_report(self, report_id: int, user_id: int) -> Report:
        report = await self.repo.get_report(report_id)
        # Not-found or not-owned (a user-scoped report of another user) → 404.
        if report is None or (report.user_id is not None and report.user_id != user_id):
            raise ReportNotFoundError()
        return report

    async def list_reports(self, user_id: int) -> list[Report]:
        return await self.repo.list_reports(user_id)

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
            rec.explanation = await self.llm.generate(system, prompt, fallback)
        return {
            "watchlist": [_rec_to_dict(r) for r in watchlist],
            "risk_alerts": [_rec_to_dict(r) for r in risk_alerts],
        }
