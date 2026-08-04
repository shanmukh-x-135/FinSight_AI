"""Prompt assembly + deterministic fallback narratives.

For each report section this produces a ``(prompt, fallback)`` pair:
* ``prompt``   — the structured facts + instruction sent to the LLM.
* ``fallback`` — a fully-formed, grounded narrative rendered directly from the
  same facts. It is the output when no LLM is configured, and the safety net if
  the LLM fails — so the pipeline always yields valid, grounded prose.
"""

from __future__ import annotations

import json

from app.intelligence.recommendation_engine import Recommendation
from config.prompts import SECTION_INSTRUCTIONS, SYSTEM_INSTRUCTION


def system_instruction() -> str:
    return SYSTEM_INSTRUCTION


def _prompt(section: str, facts: dict) -> str:
    return (
        f"{SECTION_INSTRUCTIONS[section]}\n\nFacts (JSON):\n"
        f"{json.dumps(facts, default=str, indent=2)}"
    )


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x:+.2f}%"


# --------------------------------------------------------------------------- #
# Sections                                                                    #
# --------------------------------------------------------------------------- #
def market_section(slice_: dict) -> tuple[str, str]:
    b = slice_["breadth"]
    gainers = slice_["gainers"]
    losers = slice_["losers"]
    top_g = gainers[0] if gainers else None
    top_l = losers[0] if losers else None
    fallback = (
        f"Market breadth showed {b['advancers']} advancers versus "
        f"{b['decliners']} decliners"
        + (f" (A/D ratio {b['advance_decline_ratio']:.2f})"
           if b.get("advance_decline_ratio") is not None else "")
        + "."
    )
    if top_g:
        fallback += f" Top gainer: {top_g['symbol']} ({_pct(top_g['change_percent'])})."
    if top_l:
        fallback += f" Top decliner: {top_l['symbol']} ({_pct(top_l['change_percent'])})."
    return _prompt("market", slice_), fallback


def historical_section(slice_: dict) -> tuple[str, str]:
    stats = slice_["statistics"]
    n = stats["sample_size"]
    if n == 0:
        fallback = "No comparable historical sessions had a known next-day outcome."
        return _prompt("historical", slice_), fallback
    bull = stats["bullish_probability"]
    avg = stats["avg_next_day_return"]
    fallback = (
        f"Today's conditions most resemble {len(slice_['similar_sessions'])} past "
        f"sessions. Of the {n} with a known outcome, "
        f"{round(bull * 100)}% closed higher the next day"
        + (f", averaging {avg * 100:+.2f}%" if avg is not None else "")
        + ". This is historical context, not a forecast."
    )
    return _prompt("historical", slice_), fallback


def portfolio_section(slice_: dict) -> tuple[str, str]:
    if not slice_.get("valuation_complete", True):
        symbols = ", ".join(slice_.get("unpriced_symbols") or [])
        fallback = (
            "Portfolio valuation is unavailable because current prices are missing for "
            f"{symbols or 'one or more holdings'}. Cost basis is "
            f"₹{slice_['total_cost']:,.0f}; return, allocation, health, and risk metrics "
            "are withheld until pricing is complete."
        )
        return _prompt("portfolio", slice_), fallback
    fallback = (
        f"Portfolio value ₹{slice_['total_value']:,.0f}"
        + (f", {slice_['total_return_percent']:+.2f}% overall"
           if slice_.get("total_return_percent") is not None else "")
        + f". Health score {slice_['health_score']}/100, risk {slice_['risk_level']}, "
        f"diversification {slice_['diversification_score']}/100 across "
        f"{slice_['number_of_holdings']} holdings."
    )
    return _prompt("portfolio", slice_), fallback


def recommendation_explanation(rec: Recommendation) -> tuple[str, str]:
    evidence = "; ".join(rec.evidence) if rec.evidence else "limited signals"
    risks = "; ".join(rec.risks)
    fallback = (
        f"{rec.action.title()} {rec.symbol} — confidence {rec.confidence}%. "
        f"{evidence}. Risks: {risks}."
    )
    facts = {
        "symbol": rec.symbol, "action": rec.action, "confidence": rec.confidence,
        "evidence": rec.evidence, "risks": rec.risks,
        "historical_context": rec.historical_context,
    }
    return _prompt("recommendation", facts), fallback


def executive_summary(sections: dict) -> tuple[str, str]:
    source_narratives = {
        "market": sections.get("market_summary", {}).get("narrative", ""),
        "historical": sections.get("historical_summary", {}).get("narrative", "")
        if sections.get("historical_summary") else "",
        "portfolio": sections.get("portfolio_summary", {}).get("narrative", "")
        if sections.get("portfolio_summary") else "",
    }
    source_narratives = {key: value for key, value in source_narratives.items() if value}
    parts = list(source_narratives.values())
    recs = sections.get("recommendations", [])
    watchlist = [r["symbol"] for r in recs if r["action"] == "watch"]
    watch = ", ".join(watchlist)
    fallback = " ".join(p for p in parts if p)
    if watch:
        fallback += f" Watchlist: {watch}."
    return _prompt(
        "executive",
        {"source_narratives": source_narratives, "watchlist": watchlist},
    ), fallback.strip()


def chat_response(
    *,
    question: str,
    recent_questions: list[str],
    facts: dict,
    fallback: str,
) -> tuple[str, str]:
    """Build the conversational prompt through the shared prompt infrastructure."""
    recent = " | ".join(recent_questions[-3:]) or "None"
    prompt = (
        f"{SECTION_INSTRUCTIONS['chat']}\n\n"
        f"Current user question (untrusted): {question}\n"
        f"Recent user questions (untrusted): {recent}\n\n"
        f"Facts (JSON):\n{json.dumps(facts, default=str, indent=2)}"
    )
    return prompt, fallback
