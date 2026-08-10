"""Admin-facing, read-only EOD execution status contracts."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.scheduler.constants import PipelineRunStatus, PipelineStepStatus


class PipelineStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    step_name: str
    sequence: int
    status: PipelineStepStatus
    attempt_count: int
    counters: dict[str, int]
    last_error_summary: str | None
    started_at: datetime | None
    heartbeat_at: datetime | None
    completed_at: datetime | None


class PipelineRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pipeline_name: str
    target_trading_date: date
    correlation_id: str
    status: PipelineRunStatus
    attempt_count: int
    counters: dict[str, int]
    last_error_summary: str | None
    started_at: datetime | None
    heartbeat_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    steps: list[PipelineStepOut]


class EODStatusOut(BaseModel):
    pipeline_name: str
    requested_trading_date: date | None
    run: PipelineRunOut | None
    rerun_recommended: bool
