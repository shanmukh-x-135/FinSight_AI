"""Protected operational status endpoint for the durable EOD control plane."""

from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.scheduler.constants import (
    EOD_PIPELINE_NAME,
    PipelineRunStatus,
    PipelineStepStatus,
)
from app.scheduler.models import PipelineRun, PipelineRunStep


@pytest.mark.asyncio
async def test_eod_status_requires_an_administrator(client: AsyncClient) -> None:
    response = await client.get("/api/v1/admin/jobs/eod/status")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_eod_status_reports_an_absent_target_as_retryable(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.get(
        "/api/v1/admin/jobs/eod/status?target_trading_date=2026-08-10",
        headers=admin_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["requested_trading_date"] == "2026-08-10"
    assert data["run"] is None
    assert data["rerun_recommended"] is True


@pytest.mark.asyncio
async def test_eod_status_returns_latest_run_and_step_checkpoints(
    client: AsyncClient,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    older = PipelineRun(
        pipeline_name=EOD_PIPELINE_NAME,
        target_trading_date=date(2026, 8, 7),
        correlation_id="00000000-0000-0000-0000-000000000007",
        status=PipelineRunStatus.COMPLETED,
        attempt_count=1,
    )
    latest = PipelineRun(
        pipeline_name=EOD_PIPELINE_NAME,
        target_trading_date=date(2026, 8, 10),
        correlation_id="00000000-0000-0000-0000-000000000010",
        status=PipelineRunStatus.PARTIAL,
        attempt_count=2,
        last_error_summary="history failed (RuntimeError)",
    )
    db_session.add_all([older, latest])
    await db_session.flush()
    db_session.add(
        PipelineRunStep(
            run_id=latest.id,
            step_name="market",
            sequence=0,
            status=PipelineStepStatus.COMPLETED,
            attempt_count=1,
            counters={"processed": 5},
        )
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/admin/jobs/eod/status", headers=admin_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["run"]["target_trading_date"] == "2026-08-10"
    assert data["run"]["status"] == "partial"
    assert data["run"]["steps"][0]["status"] == "completed"
    assert data["run"]["steps"][0]["counters"] == {"processed": 5}
    assert data["rerun_recommended"] is True
