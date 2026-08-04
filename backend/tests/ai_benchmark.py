"""Reusable Phase 6 AI regression benchmark runner.

Run from ``backend/`` with ``python -m tests.ai_benchmark``. Pass
``--configured-provider`` to exercise Gemini when a key and optional SDK are
available; the default deterministic narrator keeps CI reproducible.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from app.intelligence import prompt_builder as pb
from app.intelligence.explainability import validate_grounded_narrative
from app.intelligence.llm_client import (
    DeterministicNarrator,
    LLMClient,
    generate_grounded,
    get_llm_client,
)
from app.intelligence.recommendation_engine import (
    CandidateInput,
    build_recommendation,
    rank_candidates,
)
from config.prompts import PROMPT_VERSION

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ai_regression_scenarios.json"


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    description: str
    action: str
    confidence: int
    score: float
    evidence: list[str]
    risks: list[str]
    narrative: str
    checks: dict[str, bool]

    @property
    def passed(self) -> bool:
        return all(self.checks.values())


@dataclass(frozen=True)
class BenchmarkResult:
    benchmark_version: str
    prompt_version: str
    provider: str
    ranked_symbols: list[str]
    scenarios: list[ScenarioResult]

    @property
    def passed(self) -> bool:
        return all(scenario.passed for scenario in self.scenarios)


def load_scenarios(path: Path = FIXTURE_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


async def run_benchmark(llm: LLMClient | None = None) -> BenchmarkResult:
    fixture = load_scenarios()
    if fixture["prompt_version"] != PROMPT_VERSION:
        raise ValueError(
            "Benchmark prompt version does not match config.prompts.PROMPT_VERSION"
        )
    client = llm or DeterministicNarrator()
    candidates = [CandidateInput(**item["candidate"]) for item in fixture["scenarios"]]
    ranked_symbols = [rec.symbol for rec in rank_candidates(candidates)]
    results: list[ScenarioResult] = []

    for item, candidate in zip(fixture["scenarios"], candidates, strict=True):
        expected = item["expected"]
        rec = build_recommendation(candidate)
        prompt, fallback = pb.recommendation_explanation(rec)
        narrative = await generate_grounded(
            client, pb.system_instruction(), prompt, fallback
        )
        grounding = validate_grounded_narrative(narrative, prompt)
        evidence_text = " | ".join(rec.evidence)
        risk_text = " | ".join(rec.risks)
        checks = {
            "action": rec.action == expected["action"],
            "confidence": rec.confidence == expected["confidence"],
            "evidence": all(value in evidence_text for value in expected["evidence"]),
            "risks": all(value in risk_text for value in expected["risks"]),
            "grounding": grounding.valid,
            "no_price_prediction": "price target" not in narrative.lower(),
            "provider_response": (
                isinstance(client, DeterministicNarrator) or narrative != fallback
            ),
        }
        results.append(
            ScenarioResult(
                scenario_id=item["id"],
                description=item["description"],
                action=rec.action,
                confidence=rec.confidence,
                score=rec.score,
                evidence=rec.evidence,
                risks=rec.risks,
                narrative=narrative,
                checks=checks,
            )
        )

    return BenchmarkResult(
        benchmark_version=fixture["benchmark_version"],
        prompt_version=fixture["prompt_version"],
        provider=type(client).__name__,
        ranked_symbols=ranked_symbols,
        scenarios=results,
    )


def render_markdown(result: BenchmarkResult) -> str:
    status = "PASS" if result.passed else "FAIL"
    lines = [
        f"# Phase 6 AI regression benchmark — {status}",
        "",
        f"- Benchmark version: {result.benchmark_version}",
        f"- Prompt version: {result.prompt_version}",
        f"- Provider: {result.provider}",
        f"- Scenarios: {len(result.scenarios)}",
        f"- Deterministic rank order: {', '.join(result.ranked_symbols)}",
        "",
    ]
    for scenario in result.scenarios:
        scenario_status = "PASS" if scenario.passed else "FAIL"
        lines.extend(
            [
                f"## {scenario.scenario_id} — {scenario_status}",
                "",
                scenario.description,
                "",
                f"- Action: {scenario.action}",
                f"- Confidence: {scenario.confidence}%",
                f"- Score: {scenario.score:.6f}",
                f"- Evidence: {'; '.join(scenario.evidence)}",
                f"- Risks: {'; '.join(scenario.risks)}",
                f"- Narrative: {scenario.narrative}",
                "",
            ]
        )
    return "\n".join(lines)


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Run the Phase 6 AI benchmark")
    parser.add_argument(
        "--configured-provider",
        action="store_true",
        help="Use the configured LLM provider instead of DeterministicNarrator",
    )
    args = parser.parse_args()
    client = get_llm_client() if args.configured_provider else DeterministicNarrator()
    result = await run_benchmark(client)
    print(render_markdown(result))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
