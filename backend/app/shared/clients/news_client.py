"""News provider contract + an RSS implementation.

Kept behind an interface so the source can be swapped and tests inject a fake
client with no network. RSS is parsed with ``feedparser`` (blocking — callers
run it via ``asyncio.to_thread``).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import feedparser

from config.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class NewsItem:
    source: str
    url: str
    title: str
    summary: str
    published_at: datetime | None


class NewsClient(Protocol):
    def fetch(self) -> list[NewsItem]:
        """Return recent news items (may be empty; must not raise on a bad feed)."""
        ...


def _parsed_to_datetime(struct_time) -> datetime | None:
    if not struct_time:
        return None
    try:
        return datetime.fromtimestamp(calendar.timegm(struct_time), tz=timezone.utc)
    except (ValueError, OverflowError, TypeError):
        return None


class RssNewsClient:
    def __init__(self, feeds: list[str], max_per_feed: int = 50) -> None:
        self.feeds = feeds
        self.max_per_feed = max_per_feed

    def fetch(self) -> list[NewsItem]:
        items: list[NewsItem] = []
        seen_urls: set[str] = set()
        for feed_url in self.feeds:
            try:
                parsed = feedparser.parse(feed_url)
            except Exception as exc:  # noqa: BLE001 — one bad feed must not abort
                logger.warning(
                    "rss_feed_failed",
                    extra={"feed": feed_url, "error": type(exc).__name__},
                )
                continue

            source = parsed.feed.get("title", feed_url) if parsed.feed else feed_url
            for entry in parsed.entries[: self.max_per_feed]:
                url = entry.get("link")
                title = (entry.get("title") or "").strip()
                if not url or not title or url in seen_urls:
                    continue
                seen_urls.add(url)
                summary = (entry.get("summary") or entry.get("description") or "").strip()
                items.append(
                    NewsItem(
                        source=source,
                        url=url,
                        title=title,
                        summary=summary,
                        published_at=_parsed_to_datetime(entry.get("published_parsed")),
                    )
                )
        return items
