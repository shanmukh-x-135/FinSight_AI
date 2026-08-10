"""Regression tests proving the web process no longer runs a scheduler."""

from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_web_lifespan_only_disposes_web_resources(monkeypatch) -> None:
    main = import_module("app.main")
    assert not hasattr(main, "start_scheduler")
    assert not hasattr(main, "shutdown_scheduler")
    disposed = 0

    async def _dispose() -> None:
        nonlocal disposed
        disposed += 1

    monkeypatch.setattr(main, "dispose_engine", _dispose)
    async with main._lifespan(SimpleNamespace()):
        assert disposed == 0
    assert disposed == 1
