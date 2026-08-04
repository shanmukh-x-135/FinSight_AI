"""Tests for the RSS news client, with feedparser mocked (no network)."""

from __future__ import annotations

import time

from app.shared.clients import news_client as mod
from app.shared.clients.news_client import RssNewsClient


class _FakeParsed:
    def __init__(self, feed, entries):
        self.feed = feed
        self.entries = entries


def test_rss_extracts_dedupes_and_skips_invalid(monkeypatch) -> None:
    entries = [
        {"link": "http://a/1", "title": "Reliance gains", "summary": "up",
         "published_parsed": time.gmtime(0)},
        {"link": "http://a/1", "title": "Duplicate url", "summary": ""},   # dup → dropped
        {"link": "http://a/2", "title": "", "summary": "no title"},          # no title → dropped
        {"title": "no link"},                                                 # no link → dropped
        {"link": "http://a/3", "title": "TCS rallies", "summary": "strong"},
    ]
    monkeypatch.setattr(
        mod.feedparser, "parse",
        lambda url: _FakeParsed({"title": "Feed X"}, entries),
    )
    items = RssNewsClient(["http://feed"]).fetch()
    urls = [i.url for i in items]
    assert urls == ["http://a/1", "http://a/3"]
    assert items[0].source == "Feed X"
    assert items[0].published_at is not None  # parsed from published_parsed


def test_rss_bad_feed_is_skipped(monkeypatch) -> None:
    def _raise(url):
        raise RuntimeError("network down")

    monkeypatch.setattr(mod.feedparser, "parse", _raise)
    # Must not raise — a bad feed just yields no items.
    assert RssNewsClient(["http://bad"]).fetch() == []
