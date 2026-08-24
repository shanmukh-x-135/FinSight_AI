"""Grounded conversational assistant built on the Phase 6 RAG pipeline."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.constants import CONTEXT_HISTORY_LIMIT
from app.chat.repository import ChatRepository
from app.chat.schemas import (
    ChatAnswer,
    ChatExchangeOut,
    ChatHistoryMessageOut,
    ChatMessageOut,
    ChatSource,
    UserChatMessageOut,
)
from app.intelligence import prompt_builder as pb
from app.intelligence.context_builder import ContextBuilder, RagContext
from app.intelligence.generation import GenerationBudget
from app.intelligence.llm_client import (
    LLMClient,
    generate_grounded_result,
    get_llm_client,
)
from app.intelligence.recommendation_engine import (
    CandidateInput,
    Recommendation,
    build_recommendation,
    rank_candidates,
)
from config.settings import settings


@dataclass(frozen=True)
class GroundedChatDraft:
    facts: dict
    fallback: str
    evidence: list[str]
    confidence: int
    sources: list[ChatSource]
    risks: list[str]


_TOPIC_TERMS: dict[str, tuple[str, ...]] = {
    "portfolio": (
        "portfolio",
        "holding",
        "allocation",
        "diversification",
        "my risk",
    ),
    "watchlist": ("watchlist", "watch list", "tracking", "pinned"),
    "market": ("market", "breadth", "gainer", "decliner", "today"),
    "history": ("history", "historical", "similar", "analogue", "analog"),
    "news": ("news", "sentiment", "headline"),
}

_SIGNAL_TERMS = ("signal", "bullish", "bearish", "recommendation")
_BRIEF_TERMS = ("research brief", "eod brief", "end-of-day brief")
_UNCERTAINTY_TERMS = ("unavailable", "uncertain", "missing", "unknown")


def _topics(question: str, recent_questions: list[str]) -> set[str]:
    text = question.lower()
    if any(term in text for term in _BRIEF_TERMS + _UNCERTAINTY_TERMS):
        return {"portfolio", "watchlist", "market", "history", "news", "signals"}
    selected = {
        topic
        for topic, terms in _TOPIC_TERMS.items()
        if any(term in text for term in terms)
    }
    if any(term in text for term in _SIGNAL_TERMS):
        selected.update({"market", "history", "news", "signals"})
    if text.startswith("why ") and " moving" in text:
        selected.update({"market", "news", "signals"})
    if not selected and recent_questions:
        previous = recent_questions[-1].lower()
        selected = {
            topic
            for topic, terms in _TOPIC_TERMS.items()
            if any(term in previous for term in terms)
        }
    return selected or {"portfolio", "watchlist", "market"}


def _candidate_for_question(
    question: str, candidates: list[CandidateInput]
) -> CandidateInput | None:
    words = set(re.findall(r"[A-Z0-9]+", question.upper()))
    for candidate in candidates:
        symbol = candidate.symbol.upper()
        base = symbol.removesuffix(".NS").removesuffix(".BO")
        if symbol in question.upper() or base in words:
            return candidate
    return None


def _recommendation_facts(rec: Recommendation) -> dict:
    return asdict(rec)


def _source_reference(value: str | None, fallback: str = "/market") -> str:
    if value and value.lower().startswith(("https://", "http://")):
        return value
    return fallback


def _money(value: float) -> str:
    return f"₹{value:,.0f}"


def _build_draft(
    question: str, recent_questions: list[str], context: RagContext
) -> GroundedChatDraft:
    topics = _topics(question, recent_questions)
    evidence: list[str] = []
    sources: list[ChatSource] = []
    risks = ["End-of-day data may not reflect intraday moves."]
    available = 0
    selected_facts: dict = {}
    question_lower = question.lower()
    wants_uncertainty = any(term in question_lower for term in _UNCERTAINTY_TERMS)
    candidate = _candidate_for_question(question, context.candidates)

    if "portfolio" in topics:
        sources.append(
            ChatSource(
                kind="portfolio", label="Portfolio analytics", reference="/portfolio"
            )
        )
        selected_facts["portfolio"] = context.portfolio
        if context.portfolio:
            portfolio = context.portfolio
            if portfolio["number_of_holdings"] == 0:
                evidence.append(
                    "A portfolio exists, but it does not contain any holdings yet."
                )
            elif portfolio["valuation_complete"]:
                available += 1
                evidence.append(
                    f"Portfolio value is {_money(portfolio['total_value'])}; "
                    f"return is {portfolio['total_return_percent']:+.2f}%; health is "
                    f"{portfolio['health_score']:.0f}/100 with {portfolio['risk_level']} risk."
                )
            else:
                available += 1
                symbols = ", ".join(portfolio["unpriced_symbols"])
                evidence.append(
                    f"Portfolio valuation is incomplete because prices are missing for {symbols}."
                )
                risks.append(
                    "Portfolio-dependent metrics are withheld until pricing is complete."
                )
            holdings = [item["symbol"] for item in portfolio["holdings"]]
            if holdings:
                evidence.append(f"Portfolio holdings include {', '.join(holdings)}.")
            if portfolio.get("valuation_complete") and holdings:
                evidence.append(
                    "Largest holding weight is "
                    f"{portfolio['top_holding_weight_percent']:.1f}%; "
                    f"diversification is {portfolio['diversification_score']:.0f}/100 "
                    f"across {portfolio['number_of_sectors']} sectors."
                )
                top_sector = next(iter(portfolio.get("sector_allocation") or []), None)
                if top_sector:
                    risks.append(
                        f"Largest sector exposure is {top_sector['sector']} at "
                        f"{top_sector['weight_percent']:.1f}%."
                    )
                if portfolio.get("volatility_percent") is None:
                    risks.append(
                        "Portfolio volatility is unavailable because ATR coverage is incomplete."
                    )
        else:
            evidence.append("No portfolio is currently available for this account.")

    if "watchlist" in topics:
        sources.append(
            ChatSource(kind="watchlist", label="Watchlist quotes", reference="/watchlist")
        )
        selected_facts["watchlist"] = context.watchlist
        if context.watchlist:
            available += 1
            symbols = ", ".join(item["symbol"] for item in context.watchlist)
            noun = "stock" if len(context.watchlist) == 1 else "stocks"
            evidence.append(
                f"The watchlist contains {len(context.watchlist)} tracked {noun}: {symbols}."
            )
            changed = [
                item for item in context.watchlist if item["change_percent"] is not None
            ]
            if changed:
                leader = max(changed, key=lambda item: item["change_percent"])
                evidence.append(
                    f"{leader['symbol']} has the strongest latest watchlist move at "
                    f"{leader['change_percent']:+.2f}%."
                )
        else:
            evidence.append("The watchlist is currently empty.")

    if "market" in topics:
        market_date = next(
            (
                item.get("date")
                for group in ("gainers", "losers")
                for item in (context.market.get(group) or [])
                if item.get("date")
            ),
            None,
        )
        sources.append(
            ChatSource(
                kind="market",
                label=(
                    f"Market analytics ({market_date})"
                    if market_date
                    else "Market analytics"
                ),
                reference="/market",
            )
        )
        selected_facts["market"] = context.market
        breadth = context.market.get("breadth") if context.market else None
        if breadth:
            available += 1
            evidence.append(
                f"Market breadth has {breadth['advancers']} advancers, "
                f"{breadth['decliners']} decliners, and {breadth['unchanged']} unchanged."
            )
            gainers = context.market.get("gainers") or []
            losers = context.market.get("losers") or []
            if gainers:
                leader = gainers[0]
                close = (
                    f", close {_money(leader['close'])}"
                    if leader.get("close") is not None
                    else ""
                )
                session = f" on {leader['date']}" if leader.get("date") else ""
                evidence.append(
                    f"Top gainer is {leader['symbol']} at "
                    f"{leader['change_percent']:+.2f}%{close}{session}."
                )
            if losers:
                laggard = losers[0]
                close = (
                    f", close {_money(laggard['close'])}"
                    if laggard.get("close") is not None
                    else ""
                )
                session = f" on {laggard['date']}" if laggard.get("date") else ""
                evidence.append(
                    f"Top decliner is {laggard['symbol']} at "
                    f"{laggard['change_percent']:+.2f}%{close}{session}."
                )

    if "history" in topics:
        sources.append(
            ChatSource(
                kind="history", label="Historical similarity", reference="/history"
            )
        )
        selected_facts["history"] = context.history
        if context.history:
            available += 1
            stats = context.history["statistics"]
            probability = stats["bullish_probability"]
            if probability is None:
                evidence.append(
                    "Comparable sessions do not yet have enough known outcomes."
                )
            else:
                query_date = context.history.get("query_date")
                prefix = f"For {query_date}, " if query_date else ""
                evidence.append(
                    f"{prefix}{probability * 100:.0f}% of "
                    f"{stats['sample_size']} similar sessions "
                    "closed higher the next day."
                )
            risks.append("Historical analogues are scenarios, not forecasts.")
        else:
            evidence.append(
                "Historical similarity is unavailable until the index is rebuilt."
            )

    if "news" in topics:
        notable = context.news.get("notable", []) if context.news else []
        latest = notable[0] if notable else None
        sources.append(
            ChatSource(
                kind="news",
                label=(
                    f"Tagged news: {latest['source']}"
                    if latest and latest.get("source")
                    else "Tagged news sentiment"
                ),
                reference=(_source_reference(latest.get("url")) if latest else "/market"),
            )
        )
        selected_facts["news"] = context.news
        if notable:
            available += 1
            first = notable[0]
            published = (
                f" published {first['published_at']}" if first.get("published_at") else ""
            )
            evidence.append(
                f"The latest tagged headline{published} is '{first['title']}' with "
                f"{first['sentiment_label']} sentiment."
            )
        else:
            evidence.append("No company-tagged news is currently available.")

    if "signals" in topics:
        ranked = rank_candidates(context.candidates)
        bullish = next((rec for rec in ranked if rec.action == "watch"), None)
        bearish = next((rec for rec in reversed(ranked) if rec.action == "avoid"), None)
        selected = [rec for rec in (bullish, bearish) if rec is not None]
        selected_facts["signals"] = [_recommendation_facts(rec) for rec in selected]
        if selected:
            available += 1
        if bullish:
            evidence.append(
                f"Strongest bullish signal is {bullish.symbol} with "
                f"{bullish.confidence}% confidence: {'; '.join(bullish.evidence)}."
            )
        else:
            evidence.append("No candidate currently meets the bullish watch threshold.")
        if bearish:
            evidence.append(
                f"Strongest bearish signal is {bearish.symbol} with "
                f"{bearish.confidence}% confidence: {'; '.join(bearish.evidence)}."
            )
            risks.extend(bearish.risks)
        else:
            evidence.append("No candidate currently meets the bearish avoid threshold.")

    if candidate is not None:
        rec = build_recommendation(candidate)
        selected_facts["company"] = _recommendation_facts(rec)
        available += 1
        market_quote = next(
            (
                item
                for group in ("gainers", "losers")
                for item in (context.market.get(group) or [])
                if item.get("symbol") == candidate.symbol
            ),
            {},
        )
        session = f" on {market_quote['date']}" if market_quote.get("date") else ""
        evidence.append(
            f"{rec.symbol} closed at {_money(candidate.price)} and moved "
            f"{candidate.change_percent:+.2f}%{session}."
            if candidate.change_percent is not None
            else f"{rec.symbol}'s latest price change is unavailable; "
            f"the latest known close is {_money(candidate.price)}."
        )
        evidence.extend(f"{rec.symbol}: {item}." for item in rec.evidence)
        risks.extend(rec.risks)
        matching_news = [
            item
            for item in (context.news.get("notable", []) if context.news else [])
            if any(
                tag.upper()
                in {
                    candidate.symbol.upper(),
                    candidate.symbol.split(".")[0].upper(),
                }
                for tag in item.get("tags", [])
            )
        ]
        selected_facts["company_news"] = matching_news
        if not matching_news:
            risks.append(
                f"No tagged headline establishes a news cause for {rec.symbol}'s move."
            )

    if wants_uncertainty:
        unavailable: list[str] = []
        if context.portfolio is None:
            unavailable.append("portfolio")
        elif not context.portfolio.get("valuation_complete", False):
            unavailable.append("complete portfolio valuation")
        if not context.history:
            unavailable.append("historical similarity")
        if not (context.news.get("notable") if context.news else None):
            unavailable.append("company-tagged news")
        sparse = sum(
            item.rsi is None or item.ema20_distance_pct is None or item.macd_hist is None
            for item in context.candidates
        )
        if sparse:
            unavailable.append(f"complete indicators for {sparse} market candidates")
        selected_facts["unavailable"] = unavailable
        if unavailable:
            evidence.append("Unavailable data: " + ", ".join(unavailable) + ".")
        else:
            evidence.append(
                "No required slice is missing, but end-of-day data and historical "
                "analogue outcomes remain inherently uncertain."
            )

    confidence = min(85, 45 + available * 10)
    source_labels = "; ".join(source.label for source in sources)
    fallback = (
        " ".join(evidence)
        + f" Confidence {confidence}%. Sources: {source_labels}. "
        + f"Risks: {' '.join(risks)} This is research context, not investment advice."
    )
    facts = {
        # User content stays outside the facts JSON in the prompt so a number in
        # the question can never become evidence for the model's answer.
        "question": "See the untrusted user question above.",
        "context": selected_facts,
        "evidence": evidence,
        "confidence": confidence,
        "sources": [source.model_dump() for source in sources],
        "risks": risks,
    }
    return GroundedChatDraft(
        facts=facts,
        fallback=fallback,
        evidence=evidence,
        confidence=confidence,
        sources=sources,
        risks=risks,
    )


def _history_message(row) -> ChatHistoryMessageOut:
    if row.role == "assistant":
        try:
            answer = ChatAnswer.model_validate_json(row.message)
        except (ValueError, json.JSONDecodeError):
            return ChatHistoryMessageOut(
                id=row.id,
                role="assistant",
                content=row.message,
                created_at=row.created_at,
            )
        return ChatHistoryMessageOut(
            id=row.id,
            role="assistant",
            created_at=row.created_at,
            **answer.model_dump(),
        )
    return ChatHistoryMessageOut(
        id=row.id,
        role="user",
        content=row.message,
        created_at=row.created_at,
    )


class ChatService:
    def __init__(self, db: AsyncSession, llm: LLMClient | None = None) -> None:
        self.db = db
        self.repo = ChatRepository(db)
        self.llm = llm or get_llm_client()

    async def ask(self, user_id: int, question: str) -> ChatExchangeOut:
        recent = await self.repo.list_history(user_id, CONTEXT_HISTORY_LIMIT)
        recent_questions = [row.message for row in recent if row.role == "user"]
        context = await ContextBuilder(self.db).build_chat_context(user_id)
        draft = _build_draft(question, recent_questions, context)
        prompt, fallback = pb.chat_response(
            question=question,
            recent_questions=recent_questions,
            facts=draft.facts,
            fallback=draft.fallback,
        )
        generation = await generate_grounded_result(
            self.llm,
            pb.system_instruction(),
            prompt,
            fallback,
            budget=GenerationBudget(
                settings.llm_request_budget_seconds,
                settings.llm_max_provider_calls,
            ),
        )
        answer = ChatAnswer(
            content=generation.text,
            evidence=draft.evidence,
            confidence=draft.confidence,
            sources=draft.sources,
            risks=draft.risks,
            generation=generation.metadata.to_dict(),
        )

        user_row = await self.repo.add_message(user_id, "user", question)
        assistant_row = await self.repo.add_message(
            user_id, "assistant", answer.model_dump_json()
        )
        await self.db.commit()
        return ChatExchangeOut(
            user=UserChatMessageOut(
                id=user_row.id,
                content=question,
                created_at=user_row.created_at,
            ),
            assistant=ChatMessageOut(
                id=assistant_row.id,
                created_at=assistant_row.created_at,
                **answer.model_dump(),
            ),
        )

    async def history(self, user_id: int, limit: int) -> list[ChatHistoryMessageOut]:
        return [
            _history_message(row) for row in await self.repo.list_history(user_id, limit)
        ]

    async def clear_history(self, user_id: int) -> int:
        deleted = await self.repo.delete_history(user_id)
        await self.db.commit()
        return deleted
