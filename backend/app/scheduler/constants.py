"""Constants and explicit state enums for the EOD control plane."""

from __future__ import annotations

from enum import StrEnum

EOD_PIPELINE_NAME = "eod_market_intelligence"


class PipelineRunStatus(StrEnum):
    """Durable lifecycle states for one logical pipeline run."""

    PENDING = "pending"
    RUNNING = "running"
    PARTIAL = "partial"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineStepStatus(StrEnum):
    """Durable lifecycle states for an individual pipeline step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineStepName(StrEnum):
    """Ordered steps in the current EOD pipeline."""

    MARKET = "market"
    NEWS = "news"
    HISTORY = "history"


PIPELINE_STEP_ORDER = (
    PipelineStepName.MARKET,
    PipelineStepName.NEWS,
    PipelineStepName.HISTORY,
)
