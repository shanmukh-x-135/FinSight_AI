"""Tests for the one-shot production news refresh entrypoint."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.news import runner


class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


@pytest.mark.asyncio
async def test_news_runner_executes_pipeline_and_disposes_engine(monkeypatch) -> None:
    calls: list[object] = []
    disposed = 0

    class _NewsService:
        def __init__(self, db):
            calls.append(db)

        async def ingest(self):
            return SimpleNamespace(
                model_dump=lambda: {
                    "fetched": 10,
                    "new_articles": 2,
                    "tagged_articles": 1,
                    "articles_reconciled": 3,
                    "tags_added": 1,
                    "tags_removed": 4,
                    "sentiment_days_updated": 5,
                }
            )

    async def _dispose() -> None:
        nonlocal disposed
        disposed += 1

    session = _Session()
    monkeypatch.setattr(runner, "SessionFactory", lambda: session)
    monkeypatch.setattr(runner, "NewsService", _NewsService)
    monkeypatch.setattr(runner, "dispose_engine", _dispose)

    assert await runner.execute_once() == runner.EXIT_SUCCESS
    assert calls == [session]
    assert disposed == 1


@pytest.mark.asyncio
async def test_news_runner_fails_closed_and_disposes_engine(monkeypatch) -> None:
    disposed = 0

    class _NewsService:
        def __init__(self, _db):
            pass

        async def ingest(self):
            raise RuntimeError("provider response containing sensitive text")

    async def _dispose() -> None:
        nonlocal disposed
        disposed += 1

    monkeypatch.setattr(runner, "SessionFactory", _Session)
    monkeypatch.setattr(runner, "NewsService", _NewsService)
    monkeypatch.setattr(runner, "dispose_engine", _dispose)

    assert await runner.execute_once() == runner.EXIT_REFRESH_FAILED
    assert disposed == 1
