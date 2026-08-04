"""Company tagging — pure functions, no I/O.

Match a tracked stock to an article by aliases derived from its ticker and name,
using whole-word (token) matching. Aliases shorter than ``MIN_ALIAS_LEN`` or in
the stopword list are dropped to curb false positives (the roadmap's noted risk).
Tagging is best-effort and imperfect by nature — documented in docs/news-sentiment.md.
"""

from __future__ import annotations

import re

from app.news.constants import ALIAS_STOPWORDS, MIN_ALIAS_LEN

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def build_aliases(symbol: str, name: str | None) -> set[str]:
    """Derive uppercase match aliases from a ticker + company name."""
    base = symbol.split(".")[0].upper()
    candidates = {base}
    if name:
        candidates.update(t.upper() for t in _TOKEN_RE.findall(name))
    return {
        alias
        for alias in candidates
        if len(alias) >= MIN_ALIAS_LEN and alias not in ALIAS_STOPWORDS
    }


def tokenize(text: str) -> set[str]:
    """Uppercase token set of a text (for whole-word matching)."""
    return {t.upper() for t in _TOKEN_RE.findall(text or "")}


def tag_article(
    title: str, summary: str, aliases_by_stock: dict[int, set[str]]
) -> set[int]:
    """Return the set of stock ids whose aliases appear in the article text."""
    tokens = tokenize(f"{title} {summary}")
    return {
        stock_id
        for stock_id, aliases in aliases_by_stock.items()
        if aliases & tokens
    }
