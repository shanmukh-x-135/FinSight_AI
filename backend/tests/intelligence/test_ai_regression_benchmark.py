"""Dedicated 12-scenario Phase 6 AI regression benchmark."""

from __future__ import annotations

import pytest

from app.intelligence.llm_client import DeterministicNarrator
from tests.ai_benchmark import load_scenarios, run_benchmark


@pytest.mark.asyncio
async def test_ai_regression_benchmark_passes_all_scenarios() -> None:
    result = await run_benchmark(DeterministicNarrator())

    assert len(result.scenarios) == 12
    failures = {
        scenario.scenario_id: [
            name for name, passed in scenario.checks.items() if not passed
        ]
        for scenario in result.scenarios
        if not scenario.passed
    }
    assert not failures


@pytest.mark.asyncio
async def test_ai_regression_benchmark_is_reproducible() -> None:
    first = await run_benchmark(DeterministicNarrator())
    second = await run_benchmark(DeterministicNarrator())

    assert first.ranked_symbols == second.ranked_symbols
    assert [scenario.narrative for scenario in first.scenarios] == [
        scenario.narrative for scenario in second.scenarios
    ]


def test_ai_regression_fixture_has_unique_reviewable_scenarios() -> None:
    fixture = load_scenarios()
    scenario_ids = [scenario["id"] for scenario in fixture["scenarios"]]

    assert 10 <= len(scenario_ids) <= 15
    assert len(scenario_ids) == len(set(scenario_ids))
    assert all(scenario["description"].strip() for scenario in fixture["scenarios"])
