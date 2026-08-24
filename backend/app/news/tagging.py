"""Company tagging — pure functions, no I/O.

Match a tracked stock to an article by aliases derived from its ticker and name,
using whole-word (token) matching. Aliases shorter than ``MIN_ALIAS_LEN`` or in
the stopword list are dropped to curb false positives (the roadmap's noted risk).
Tagging is best-effort and imperfect by nature — documented in docs/news-sentiment.md.
"""

from __future__ import annotations

import re

from app.news.constants import ALIAS_STOPWORDS, COMPANY_ALIASES, MIN_ALIAS_LEN

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _normalize_phrase(text: str) -> str:
    """Normalize punctuation and whitespace while preserving token order."""
    return " ".join(token.upper() for token in _TOKEN_RE.findall(text or ""))


def build_aliases(symbol: str, name: str | None) -> set[str]:
    """Build reviewed phrases plus safe ticker/full-name fallbacks.

    Individual company-name tokens are deliberately not aliases: after the
    universe grew they caused broad words such as ``OIL``, ``LIFE`` and
    ``TECH`` to link unrelated coverage to equities.
    """
    base = symbol.split(".")[0].upper()
    candidates = {base, *COMPANY_ALIASES.get(base, ())}
    if name:
        name_tokens = [
            token
            for token in _TOKEN_RE.findall(name.upper())
            if token not in {"LTD", "LIMITED", "INC", "CORP", "CORPORATION", "CO"}
        ]
        if name_tokens:
            candidates.add(" ".join(name_tokens))
    return {
        normalized
        for alias in candidates
        if (normalized := _normalize_phrase(alias))
        and len(normalized.replace(" ", "")) >= MIN_ALIAS_LEN
        and normalized not in ALIAS_STOPWORDS
    }


def tokenize(text: str) -> set[str]:
    """Uppercase token set of a text (for whole-word matching)."""
    return {t.upper() for t in _TOKEN_RE.findall(text or "")}


def tag_article(
    title: str, summary: str, aliases_by_stock: dict[int, set[str]]
) -> set[int]:
    """Return the set of stock ids whose aliases appear in the article text."""
    normalized_text = f" {_normalize_phrase(f'{title} {summary}')} "
    return {
        stock_id
        for stock_id, aliases in aliases_by_stock.items()
        if any(f" {alias} " in normalized_text for alias in aliases)
    }
