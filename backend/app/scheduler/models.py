"""Durable execution-state models for the EOD control plane."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.scheduler.constants import PipelineRunStatus, PipelineStepStatus
from app.shared.database import Base


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class PipelineRun(Base):
    """One logical execution for a pipeline and target trading date."""

    __tablename__ = "pipeline_runs"
    __table_args__ = (
        UniqueConstraint(
            "pipeline_name",
            "target_trading_date",
            name="uq_pipeline_runs_name_target_date",
        ),
        Index("ix_pipeline_runs_status_heartbeat", "status", "heartbeat_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_name: Mapped[str] = mapped_column(String(100), nullable=False)
    target_trading_date: Mapped[date] = mapped_column(Date, nullable=False)
    correlation_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, nullable=False
    )
    status: Mapped[PipelineRunStatus] = mapped_column(
        Enum(
            PipelineRunStatus,
            name="pipeline_run_status",
            values_callable=lambda e: [v.value for v in e],
        ),
        default=PipelineRunStatus.PENDING,
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    counters: Mapped[dict[str, int]] = mapped_column(JSON, default=dict, nullable=False)
    last_error_summary: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
        nullable=False,
    )

    steps: Mapped[list["PipelineRunStep"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="PipelineRunStep.sequence",
    )


class PipelineRunStep(Base):
    """Execution state for one independently committed pipeline step."""

    __tablename__ = "pipeline_run_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "step_name", name="uq_pipeline_run_steps_run_step"),
        Index("ix_pipeline_run_steps_status_heartbeat", "status", "heartbeat_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_name: Mapped[str] = mapped_column(String(50), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PipelineStepStatus] = mapped_column(
        Enum(
            PipelineStepStatus,
            name="pipeline_step_status",
            values_callable=lambda e: [v.value for v in e],
        ),
        default=PipelineStepStatus.PENDING,
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    counters: Mapped[dict[str, int]] = mapped_column(JSON, default=dict, nullable=False)
    last_error_summary: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
        nullable=False,
    )

    run: Mapped[PipelineRun] = relationship(back_populates="steps")
